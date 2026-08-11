import AuthForm from "@/components/auth-form";

export const metadata = { title: "Sign in - driftline" };

// a signed in reader never reaches this page: proxy.ts sends them to the app before it renders
export default function LoginPage() {
  return <AuthForm mode="login" />;
}
