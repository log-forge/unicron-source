import mongoose, { Schema, type Document, type Model, type Types } from 'mongoose';

export interface IUser extends Document<Types.ObjectId> {
  email: string;
  emailVerified: boolean;
  name?: string;
  username?: string;
  displayUsername?: string;
  image?: string;
  requiresPasswordChange?: boolean;
  createdAt: Date;
  updatedAt: Date;
  id?: string;
}

const UserSchema = new Schema<IUser>(
  {
    email: { type: String, required: true, unique: true, index: true, lowercase: true, trim: true },
    emailVerified: { type: Boolean, required: true, default: true },
    name: { type: String, required: false, trim: true },
    username: { type: String, required: false, unique: true, sparse: true, index: true, lowercase: true, trim: true },
    displayUsername: { type: String, required: false, trim: true },
    image: { type: String, required: false },
    requiresPasswordChange: { type: Boolean, required: false, default: false },
  },
  { collection: 'user', timestamps: true },
);

UserSchema.virtual('id').get(function () {
  return this._id.toString();
});

UserSchema.set('toJSON', {
  virtuals: true,
  transform: (_doc, ret) => {
    const { _id, __v, ...rest } = ret;
    return { ...rest, id: _id?.toString() };
  },
});

export const UserModel: Model<IUser> = (mongoose.models.user as Model<IUser>) || mongoose.model<IUser>('user', UserSchema);
