"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LockKeyhole } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useRouter } from "@/i18n/navigation";
import { login } from "@/lib/api/client";
import { safeNext } from "@/lib/navigation";
import { errorMessage } from "@/lib/errors";
import { startSession, useSession } from "@/lib/session";

export function LoginForm() {
  const t = useTranslations();
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { me } = useSession();

  // Уже вошли (например, открыли /login из закладки) — сразу в систему
  useEffect(() => {
    if (me) router.replace(safeNext(params.get("next")));
  }, [me, params, router]);

  const mutation = useMutation({
    mutationFn: () => login(username, password),
    onSuccess: (me) => {
      startSession(queryClient, me);
      router.replace(safeNext(params.get("next")));
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <section className="mx-auto flex max-w-sm flex-col gap-6 py-6 sm:py-12">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="flex size-12 items-center justify-center rounded-card bg-primary text-primary-fg">
          <LockKeyhole className="size-5" aria-hidden />
        </span>
        <h1 className="text-2xl font-semibold text-fg">{t("login.title")}</h1>
        <p className="text-sm text-fg-muted">{t("login.subtitle")}</p>
      </div>
      <form
        onSubmit={submit}
        className="flex flex-col gap-4 rounded-card-lg border border-border p-6"
        aria-describedby={mutation.isError ? "login-error" : undefined}
      >
        <Field id="username" label={t("login.username")}>
          <Input
            id="username"
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </Field>
        <Field id="password" label={t("login.password")}>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        {mutation.isError && (
          <Alert tone="error" id="login-error">
            {errorMessage(mutation.error, t)}
          </Alert>
        )}
        <Button type="submit" size="lg" disabled={mutation.isPending}>
          {mutation.isPending ? t("login.submitting") : t("login.submit")}
        </Button>
      </form>
      <p className="text-center text-xs text-fg-muted">{t("login.notice")}</p>
    </section>
  );
}
