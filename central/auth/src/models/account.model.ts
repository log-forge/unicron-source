import mongoose, { Schema, type Document, type Model, type Types } from 'mongoose';

export interface IAccount extends Document<Types.ObjectId> {
  userId: Types.ObjectId;
  accountId: string;
  providerId: string;
  accessToken?: string;
  refreshToken?: string;
  accessTokenExpiresAt?: Date;
  refreshTokenExpiresAt?: Date;
  scope?: string;
  idToken?: string;
  password?: string;
  createdAt: Date;
  updatedAt: Date;
  id?: string;
}

const AccountSchema = new Schema<IAccount>(
  {
    userId: { type: Schema.Types.ObjectId, ref: 'user', required: true, index: true },
    accountId: { type: String, required: true },
    providerId: { type: String, required: true, index: true },
    accessToken: { type: String, required: false, index: true },
    refreshToken: { type: String, required: false },
    accessTokenExpiresAt: { type: Date, required: false },
    refreshTokenExpiresAt: { type: Date, required: false },
    scope: { type: String, required: false },
    idToken: { type: String, required: false },
    password: { type: String, required: false },
  },
  { collection: 'account', timestamps: true },
);

AccountSchema.virtual('id').get(function () {
  return this._id.toString();
});

AccountSchema.set('toJSON', {
  virtuals: true,
  transform: (_doc, ret) => {
    const { _id, __v, ...rest } = ret;
    return { ...rest, id: _id?.toString() };
  },
});

export const AccountModel: Model<IAccount> = (mongoose.models.account as Model<IAccount>) || mongoose.model<IAccount>('account', AccountSchema);
