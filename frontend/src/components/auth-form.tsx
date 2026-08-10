"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FC, type FormEvent, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";

interface AuthFormProps {
  mode: "login" | "register";
}

const COPY = {
  login: {
    heading: "Sign in",
    action: "Sign in",
    pending: "Signing in",
    switchText: "No account yet?",
    switchHref: "/register",
    switchLabel: "Create one",
  },
  register: {
    heading: "Create an account",
    action: "Create account",
    pending: "Creating account",
    switchText: "Already have an account?",
    switchHref: "/login",
    switchLabel: "Sign in",
  },
} as const;

const AuthForm: FC<AuthFormProps> = ({ mode }) => {
  const router = useRouter();
  const { signIn, register } = useAuth();
  const copy = COPY[mode];

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  // stays true through navigation, so the button cannot be pressed twice while routing
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFieldError(null);
    setPending(true);
    try {
      if (mode === "login") {
        await signIn(email, password);
      } else {
        await register(email, password);
      }
      router.push("/app/datasets");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFieldError(caught.field ?? null);
      } else {
        setError("Something went wrong. Try again.");
      }
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex w-full max-w-sm flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <h1 className="font-medium text-xl tracking-tight">{copy.heading}</h1>
        <p className="text-muted-foreground text-sm">
          Sequences and runs are scoped to your account.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={fieldError === "email"}
          required
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-invalid={fieldError === "password"}
          required
        />
        {mode === "register" ? (
          <p className="text-muted-foreground text-xs">At least 8 characters.</p>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}

      <Button type="submit" disabled={pending} className="w-full">
        {pending ? copy.pending : copy.action}
      </Button>

      <p className="text-muted-foreground text-sm">
        {copy.switchText}{" "}
        <Link href={copy.switchHref} className="text-foreground underline underline-offset-4">
          {copy.switchLabel}
        </Link>
      </p>
    </form>
  );
};

export default AuthForm;
