import AuthForm from "@/components/auth-form";
import RedirectWhenSignedIn from "@/components/redirect-when-signed-in";

export const metadata = { title: "Sign in - driftline" };

export default function LoginPage() {
  return (
    <RedirectWhenSignedIn>
      <AuthForm mode="login" />
    </RedirectWhenSignedIn>
  );
}
