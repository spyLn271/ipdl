"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { type FormEvent, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { createUser, listPartners, listUsers, updateUser } from "@/lib/api/client";
import { ROLES, type Role, type User } from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";
import { errorMessage } from "@/lib/errors";
import { useSession } from "@/lib/session";

function CreateUserDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const partners = useQuery({ queryKey: ["partners"], queryFn: listPartners, enabled: open });
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [partnerId, setPartnerId] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      createUser({
        username: username.trim(),
        display_name: displayName.trim(),
        password,
        role,
        partner_id: role === "partner" ? partnerId || null : null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      onOpenChange(false);
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <form onSubmit={submit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>{t("admin.createUser")}</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Field id="u-username" label={t("admin.username")} required>
              <Input
                id="u-username"
                value={username}
                autoComplete="off"
                pattern="[A-Za-z0-9._\-]+"
                minLength={3}
                maxLength={64}
                required
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field id="u-name" label={t("admin.displayName")} required>
              <Input
                id="u-name"
                value={displayName}
                minLength={2}
                maxLength={200}
                required
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </Field>
            <Field
              id="u-password"
              label={t("admin.password")}
              hint={t("admin.passwordHint")}
              required
            >
              <Input
                id="u-password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={password}
                aria-describedby="u-password-hint"
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="u-role" label={t("admin.role")}>
                <NativeSelect
                  id="u-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as Role)}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`roles.${r}`)}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              {role === "partner" && (
                <Field id="u-partner" label={t("admin.partner")} required>
                  <NativeSelect
                    id="u-partner"
                    value={partnerId}
                    required
                    onChange={(e) => setPartnerId(e.target.value)}
                  >
                    <option value="" disabled>
                      {t("requestDialog.partnerPlaceholder")}
                    </option>
                    {(partners.data ?? []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {countryName(p.country, locale)} · {p.name}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              )}
            </div>
            {mutation.isError && <Alert tone="error">{errorMessage(mutation.error, t)}</Alert>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {t("admin.create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const t = useTranslations();
  const [password, setPassword] = useState("");
  const mutation = useMutation({
    mutationFn: () => updateUser(user.id, { password }),
    onSuccess: onClose,
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent closeLabel={t("common.close")}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
          className="flex min-h-0 flex-col"
        >
          <DialogHeader>
            <DialogTitle>{t("admin.newPassword", { user: user.username })}</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Field
              id="reset-password"
              label={t("admin.password")}
              hint={t("admin.passwordHint")}
              required
            >
              <Input
                id="reset-password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={password}
                aria-describedby="reset-password-hint"
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {mutation.isError && <Alert tone="error">{errorMessage(mutation.error, t)}</Alert>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UsersSection() {
  const t = useTranslations();
  const format = useFormatter();
  const locale = useLocale();
  const { me } = useSession();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const [creating, setCreating] = useState(false);
  const [resetting, setResetting] = useState<User | null>(null);
  const toggle = useMutation({
    mutationFn: (user: User) => updateUser(user.id, { is_active: !user.is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <section aria-labelledby="admin-users" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="admin-users" className="text-lg font-semibold text-fg">
          {t("admin.users")}
        </h2>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus aria-hidden />
          {t("admin.createUser")}
        </Button>
      </div>
      {toggle.isError && <Alert tone="error">{errorMessage(toggle.error, t)}</Alert>}
      {users.isPending ? (
        <Skeleton className="h-40" />
      ) : users.isError ? (
        <Alert tone="error">{errorMessage(users.error, t)}</Alert>
      ) : (
        <div className="overflow-x-auto rounded-card border border-border">
          <table className="w-full min-w-[46rem] text-left text-sm">
            <thead className="border-b border-border bg-bg-subtle text-xs">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("admin.username")}
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("admin.role")}
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("admin.partner")}
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("admin.lastLogin")}
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("admin.active")}
                </th>
                <th scope="col" className="px-4 py-3 text-right font-medium">
                  {t("common.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.data.map((user) => (
                <tr key={user.id}>
                  <td className="px-4 py-3">
                    <span className="font-medium text-fg">{user.display_name}</span>
                    <span className="block font-mono text-xs text-fg-muted">{user.username}</span>
                  </td>
                  <td className="px-4 py-3">{t(`roles.${user.role}`)}</td>
                  <td className="px-4 py-3 text-xs">
                    {user.partner
                      ? `${countryName(user.partner.country, locale)} · ${user.partner.name}`
                      : t("admin.partnerNone")}
                  </td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap text-fg-muted">
                    {user.last_login_at
                      ? format.dateTime(new Date(user.last_login_at), {
                          dateStyle: "short",
                          timeStyle: "short",
                        })
                      : t("admin.never")}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={user.is_active ? "ok" : "neutral"}>
                      {user.is_active ? t("admin.active") : t("admin.inactive")}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <span className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setResetting(user)}>
                        <KeyRound aria-hidden />
                        {t("admin.resetPassword")}
                      </Button>
                      {user.id !== me?.user.id && (
                        <Button
                          size="sm"
                          variant={user.is_active ? "danger" : "secondary"}
                          disabled={toggle.isPending}
                          onClick={() => toggle.mutate(user)}
                        >
                          {user.is_active ? t("admin.deactivate") : t("admin.activate")}
                        </Button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {creating && <CreateUserDialog open onOpenChange={setCreating} />}
      {resetting && <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />}
    </section>
  );
}
