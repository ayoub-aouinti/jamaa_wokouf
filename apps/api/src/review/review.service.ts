import { BadRequestException, ConflictException, Injectable, NotFoundException } from '@nestjs/common';
import { DatabaseService } from '../db/database.service.js';
import { RULING_FULL_COLS, rulingBriefJson, rulingFullJson } from '../common/sql.js';
import { ReviewLogService } from './review-log.service.js';

export type Decision = 'verify' | 'reject';

const REJECT_PREFIX = 'رُدَّ في المراجعة: ';

@Injectable()
export class ReviewService {
  constructor(
    private readonly db: DatabaseService,
    private readonly log: ReviewLogService,
  ) {}

  /**
   * طابورُ المراجعة: الأحكامُ المقترَحةُ التي لم يُقضَ فيها بعد، على ترتيب
   * المصحف. ومع كلِّ حكمٍ ما يقوله غيرُه في الموضع نفسه — للاستئناس، ولا
   * يُحتجّ به على الكتاب، ولا يُحسَب منه اتفاق.
   */
  async queue(source: string | undefined, limit: number, after?: { seq: number; source: string }) {
    const logged = await this.log.available();
    const params: unknown[] = [];
    const where = [`r.status = 'proposed'`];
    if (source) {
      params.push(source);
      where.push(`r.source = $${params.length}`);
    }
    if (logged) {
      where.push(`NOT EXISTS (SELECT 1 FROM review_log l WHERE l.entity = 'ruling'
                    AND l.key @> jsonb_build_object('seq', r.seq, 'source', r.source))`);
    }
    const countWhere = where.join(' AND ');
    if (after) {
      params.push(after.seq, after.source);
      where.push(`(r.seq, r.source) > ($${params.length - 1}, $${params.length})`);
    }
    params.push(limit);

    const items = await this.db.query<{ word: unknown; ruling: unknown; others: unknown }>(
      `SELECT json_build_object('seq', w.seq, 'sura', w.sura, 'sura_name', w.sura_name,
                                'ayah', w.ayah, 'wpos', w.wpos, 'text', w.text) AS word,
              ${rulingFullJson('q')} AS ruling,
              (SELECT COALESCE(json_agg(${rulingBriefJson('o')} ORDER BY o.source), '[]')
                 FROM rulings o WHERE o.seq = q.seq AND o.source <> q.source) AS others
         FROM (SELECT r.* FROM rulings r WHERE ${where.join(' AND ')}
                ORDER BY r.seq, r.source LIMIT $${params.length}) q
         JOIN words w ON w.seq = q.seq
        ORDER BY q.seq, q.source`,
      params,
    );

    const countParams = source ? [source] : [];
    const remaining = await this.db.one<{ n: number }>(
      `SELECT count(*) AS n FROM rulings r WHERE ${countWhere}`,
      countParams,
    );
    return { items, remaining: remaining?.n ?? 0 };
  }

  /**
   * قرارُ المراجِع في حكمٍ واحد. الاعتمادُ يرفع الحالَ إلى verified.
   * والردُّ لا يحذف الحكم ولا يُخفيه: يبقى مقترَحاً، ويُضاف سببُ الردّ إلى
   * review بعد ما فيه — فما كان فيه من تعليمٍ سابقٍ لا يُمحى.
   */
  async decide(seq: number, source: string, decision: Decision, reason: string | undefined, actor: string) {
    await this.log.require();
    if (decision === 'reject' && !reason?.trim()) {
      throw new BadRequestException('الردُّ يحتاج سبباً يُثبَت مع الحكم.');
    }
    return this.db.tx(async (c) => {
      const cur = await c.query(
        `SELECT ${RULING_FULL_COLS} FROM rulings r WHERE r.seq = $1 AND r.source = $2 FOR UPDATE`,
        [seq, source],
      );
      const before = cur.rows[0];
      if (!before) throw new NotFoundException('لا حكمَ لهذا المصدر في هذا الموضع.');
      if (before.status === 'verified') throw new ConflictException('الحكمُ محقَّقٌ من قبل.');

      let after;
      if (decision === 'verify') {
        const r = await c.query(
          `UPDATE rulings r SET status = 'verified' WHERE seq = $1 AND source = $2
           RETURNING ${RULING_FULL_COLS}`,
          [seq, source],
        );
        after = r.rows[0];
      } else {
        const r = await c.query(
          `UPDATE rulings r
              SET review = CASE WHEN review IS NULL OR review = '' THEN $3
                                ELSE review || ' · ' || $3 END
            WHERE seq = $1 AND source = $2
           RETURNING ${RULING_FULL_COLS}`,
          [seq, source, REJECT_PREFIX + reason!.trim()],
        );
        after = r.rows[0];
      }

      await this.log.write(c, {
        actor,
        entity: 'ruling',
        key: { seq, source },
        action: decision,
        before,
        after,
        reason: reason?.trim() || null,
      });
      return { ok: true as const };
    });
  }
}

