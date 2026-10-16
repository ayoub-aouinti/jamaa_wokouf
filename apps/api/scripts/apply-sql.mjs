#!/usr/bin/env node
// يُطبِّق ملفَّ SQL على القاعدة المعرَّفة في DATABASE_URL (من apps/api/.env).
//   node apps/api/scripts/apply-sql.mjs db/app_schema.sql
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

const envFile = fileURLToPath(new URL('../.env', import.meta.url));
if (existsSync(envFile)) process.loadEnvFile(envFile);

const file = process.argv[2];
if (!file) {
  console.error('الاستعمال: apply-sql.mjs <ملف.sql>');
  process.exit(2);
}
if (!process.env.DATABASE_URL) {
  console.error('DATABASE_URL غيرُ معرَّف. انسخ apps/api/.env.example إلى apps/api/.env.');
  process.exit(2);
}

const client = new pg.Client({ connectionString: process.env.DATABASE_URL });
await client.connect();
try {
  await client.query(readFileSync(file, 'utf8'));
  console.log(`طُبِّق ${file}`);
} finally {
  await client.end();
}
