import AuthForm from "@/components/auth-form";
import RedirectWhenSignedIn from "@/components/redirect-when-signed-in";

export const metadata = { title: "Create an account - driftline" };

export default function RegisterPage() {
  return (
    <RedirectWhenSignedIn>
      <AuthForm mode="register" />
    </RedirectWhenSignedIn>
  );
}
