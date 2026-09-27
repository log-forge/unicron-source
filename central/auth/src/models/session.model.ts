import mongoose, { Schema, type Document, type Model, type Types } from 'mongoose';

export interface ISession extends Document<Types.ObjectId> {
  userId: Types.ObjectId;
  token: string;
  expiresAt: Date;
  ipAddress?: string;
  userAgent?: string;
  createdAt: Date;
  updatedAt: Date;
  id?: string;
}

const SessionSchema = new Schema<ISession>(
  {
    userId: { type: Schema.Types.ObjectId, ref: 'user', required: true, index: true },
    token: { type: String, required: true, unique: true },
    expiresAt: { type: Date, required: true, index: true },
    ipAddress: { type: String, required: false },
    userAgent: { type: String, required: false },
  },
  { collection: 'session', timestamps: true },
);

SessionSchema.virtual('id').get(function () {
  return this._id.toString();
});

SessionSchema.set('toJSON', {
  virtuals: true,
  transform: (_doc, ret) => {
    const { _id, __v, ...rest } = ret;
    return { ...rest, id: _id?.toString() };
  },
});

export const SessionModel: Model<ISession> = (mongoose.models.session as Model<ISession>) || mongoose.model<ISession>('session', SessionSchema);
