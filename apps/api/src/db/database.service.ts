import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import pg from 'pg';

// أعدادُ Postgres الكبيرة (bigint/count) تأتي نصّاً افتراضاً؛ وكلُّ أعدادنا
// دون حدِّ الدقّة في JavaScript، فتُقرأ أعداداً.
pg.types.setTypeParser(20, (v) => Number(v));

/**
 * الوصولُ إلى قاعدة Postgres. لا ORM هنا عمداً: المخطَّطُ مكتوبٌ في
 * db/schema.sql وعليه تعليقاتُ قيوده المقصودة، فلا يُترَك لأداةٍ أن تُزامِنه
 * أو تُشدِّده.
 */
@Injectable()
export class DatabaseService implements OnModuleDestroy {
  private readonly log = new Logger('Database');
  readonly pool: pg.Pool;

  constructor() {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error('DATABASE_URL غيرُ معرَّف. انسخ apps/api/.env.example إلى apps/api/.env واملأه.');
    }
    if (/\/\/USER:PASSWORD@/.test(connectionString)) {
      throw new Error('DATABASE_URL في apps/api/.env ما زال مثالَ .env.example (USER:PASSWORD). ضع مستخدمَ Postgres وكلمةَ سرِّه.');
    }
    this.pool = new pg.Pool({
      connectionString,
      max: Number(process.env.PG_POOL_MAX ?? 10),
      application_name: 'jamei-api',
    });
    this.pool.on('error', (err) => this.log.error(err.message));
  }

  async query<T extends pg.QueryResultRow = pg.QueryResultRow>(
    text: string,
    params: unknown[] = [],
  ): Promise<T[]> {
    const res = await this.pool.query<T>(text, params);
    return res.rows;
  }

  async one<T extends pg.QueryResultRow = pg.QueryResultRow>(
    text: string,
    params: unknown[] = [],
  ): Promise<T | undefined> {
    const rows = await this.query<T>(text, params);
    return rows[0];
  }

  /** يُنفِّذ fn في معاملةٍ واحدة: إمّا أن يقع كلُّه أو لا يقع منه شيء. */
  async tx<T>(fn: (c: pg.PoolClient) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      const out = await fn(client);
      await client.query('COMMIT');
      return out;
    } catch (e) {
      await client.query('ROLLBACK');
      throw e;
    } finally {
      client.release();
    }
  }

  async onModuleDestroy() {
    await this.pool.end();
  }
}
