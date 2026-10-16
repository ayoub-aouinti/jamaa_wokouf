import 'reflect-metadata';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Logger } from '@nestjs/common';
import { HttpAdapterHost, NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';
import { NoStoreOnErrorFilter } from './common/no-store.filter.js';

// apps/api/.env إن وُجد — بلا حزمةٍ إضافية (Node ≥ 20.12)
const envFile = fileURLToPath(new URL('../.env', import.meta.url));
if (existsSync(envFile)) process.loadEnvFile(envFile);

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { logger: ['error', 'warn', 'log'] });
  app.setGlobalPrefix('api');
  app.useGlobalFilters(new NoStoreOnErrorFilter(app.get(HttpAdapterHost).httpAdapter));

  // الويبُ والجوالُ من أصولٍ أخرى. CORS_ORIGINS قائمةٌ مفصولةٌ بفواصل، و«*» للتطوير.
  const origins = (process.env.CORS_ORIGINS ?? 'http://localhost:5173')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  app.enableCors({
    origin: origins.includes('*') ? true : origins,
    methods: ['GET', 'POST', 'PATCH'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    maxAge: 600,
  });
  app.enableShutdownHooks();

  const port = Number(process.env.PORT ?? 3000);
  await app.listen(port, process.env.HOST ?? '0.0.0.0');
  new Logger('Jamei').log(`الواجهةُ البرمجية على http://localhost:${port}/api`);
}

void bootstrap();
