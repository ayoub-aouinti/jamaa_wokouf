import { BadRequestException, Body, Controller, Get, HttpCode, Param, Post, Query, Req, UseGuards } from '@nestjs/common';
import { AdminGuard } from '../common/admin.guard.js';
import { idParam, intParam } from '../common/params.js';
import { ReviewService, type Decision } from './review.service.js';

@Controller()
export class ReviewController {
  constructor(private readonly review: ReviewService) {}

  /** الطابورُ قراءةٌ، فلا يُشترَط له رمز. */
  @Get('review/queue')
  queue(@Query('source') source?: string, @Query('limit') limit?: string, @Query('after') after?: string) {
    let cursor: { seq: number; source: string } | undefined;
    if (after) {
      const [seq, src] = after.split(':');
      cursor = { seq: intParam(seq, 'after.seq', { min: 0 }), source: idParam(src, 'after.source') };
    }
    return this.review.queue(
      source ? idParam(source, 'source') : undefined,
      intParam(limit, 'limit', { min: 1, max: 100, fallback: 20 }),
      cursor,
    );
  }

  @Post('review/:seq/:source')
  @HttpCode(200)
  @UseGuards(AdminGuard)
  decide(
    @Param('seq') seq: string,
    @Param('source') source: string,
    @Body() body: { decision?: string; reason?: string } | undefined,
    @Req() req: { actor: string },
  ) {
    const decision = body?.decision;
    if (decision !== 'verify' && decision !== 'reject') {
      throw new BadRequestException('decision إمّا verify وإمّا reject.');
    }
    if (body?.reason !== undefined && typeof body.reason !== 'string') {
      throw new BadRequestException('reason نصّ.');
    }
    if (body?.reason && body.reason.length > 2000) throw new BadRequestException('السببُ أطولُ من اللازم.');
    return this.review.decide(
      intParam(seq, 'seq', { min: 1 }),
      idParam(source, 'source'),
      decision as Decision,
      body?.reason,
      req.actor,
    );
  }

  /** يتحقَّق من رمز المراجِع دون أن يكتب شيئاً. */
  @Post('auth/check')
  @HttpCode(200)
  @UseGuards(AdminGuard)
  check(@Req() req: { actor: string }) {
    return { ok: true, actor: req.actor };
  }
}
