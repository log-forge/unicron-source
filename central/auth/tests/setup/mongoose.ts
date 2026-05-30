import mongoose from 'mongoose';
import { connectMongoose, disconnectMongoose } from '../../src/db/mongoose';
import { env } from '../../src/config/env';

const DEFAULT_TEST_DB_NAME = 'central_auth_test';

export async function startTestMongo() {
  const uri = process.env.CENTRAL_AUTH_TEST_MONGODB_URI;
  const dbName = process.env.CENTRAL_AUTH_TEST_MONGODB_DB_NAME || DEFAULT_TEST_DB_NAME;

  if (!uri) {
    throw new Error(
      'CENTRAL_AUTH_TEST_MONGODB_URI is required for central-auth integration tests. Run `make test-central-auth` from the repository root.',
    );
  }

  env.MONGODB_URI = uri;
  env.MONGODB_DB_NAME = dbName;
  env.MONGODB_TLS = false;
  env.MONGODB_RETRY_WRITES = false;

  await connectMongoose({
    uri,
    dbName: env.MONGODB_DB_NAME,
    retryWrites: false,
    tls: false,
    minPoolSize: 1,
    maxPoolSize: 5,
  });
}

export async function dropTestDatabase() {
  if (mongoose.connection.readyState !== 1) return;
  const expectedDbName = process.env.CENTRAL_AUTH_TEST_MONGODB_DB_NAME || DEFAULT_TEST_DB_NAME;
  const activeDbName = mongoose.connection.db?.databaseName;

  if (activeDbName !== expectedDbName) {
    throw new Error(
      `Refusing to clear MongoDB database "${activeDbName ?? 'unknown'}"; expected test database "${expectedDbName}".`,
    );
  }

  const collections = await mongoose.connection.db?.collections();
  if (!collections) return;

  for (const collection of collections) {
    await collection.deleteMany({});
  }
}

export async function stopTestMongo() {
  await disconnectMongoose();
}
