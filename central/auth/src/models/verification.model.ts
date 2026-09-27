import mongoose, { Schema, type Document, type Model, type Types } from 'mongoose';

export interface IVerification extends Document<Types.ObjectId> {
  identifier: string;
  value: string;
  expiresAt: Date;
  createdAt: Date;
  updatedAt: Date;
  id?: string;
}

const VerificationSchema = new Schema<IVerification>(
  {
    identifier: { type: String, required: true, index: true },
    value: { type: String, required: true },
    expiresAt: { type: Date, required: true, index: true },
  },
  { collection: 'verification', timestamps: true },
);

VerificationSchema.virtual('id').get(function () {
  return this._id.toString();
});

VerificationSchema.set('toJSON', {
  virtuals: true,
  transform: (_doc, ret) => {
    const { _id, __v, ...rest } = ret;
    return { ...rest, id: _id?.toString() };
  },
});

export const VerificationModel: Model<IVerification> =
  (mongoose.models.verification as Model<IVerification>) || mongoose.model<IVerification>('verification', VerificationSchema);
