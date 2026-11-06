"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useRouter } from "@/i18n/navigation";
import { changePassword } from "@/lib/api/client";
import { errorMessage } from "@/lib/errors";
import { endSession } from "@/lib/session";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChangePasswordDialog({ open, onOpenChange }: Props) {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && next !== confirm;

  const mutation = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: () => {
      // Сервер закрыл все сессии пользователя — войти заново
      void endSession(queryClient);
      router.replace("/login");
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) return;
    mutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <form onSubmit={submit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>{t("password.title")}</DialogTitle>
            <DialogDescription>{t("password.hint")}</DialogDescription>
          </DialogHeader>
          <DialogBody>
            <Field id="pw-current" label={t("password.current")} required>
              <Input
                id="pw-current"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </Field>
            <Field id="pw-new" label={t("password.new")} required>
              <Input
                id="pw-new"
                type="password"
                autoComplete="new-password"
                minLength={12}
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
              />
            </Field>
            <Field
              id="pw-confirm"
              label={t("password.confirm")}
              error={mismatch ? t("password.mismatch") : null}
              required
            >
              <Input
                id="pw-confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                aria-invalid={mismatch || undefined}
                aria-describedby={mismatch ? "pw-confirm-error" : undefined}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </Field>
            {mutation.isError && <Alert tone="error">{errorMessage(mutation.error, t)}</Alert>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={mutation.isPending || mismatch}>
              {mutation.isPending ? t("common.saving") : t("password.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
