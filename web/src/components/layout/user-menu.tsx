"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogOut, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { ChangePasswordDialog } from "@/components/auth/change-password-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useRouter } from "@/i18n/navigation";
import { logout } from "@/lib/api/client";
import { endSession, useSession } from "@/lib/session";

export function UserMenu() {
  const t = useTranslations();
  const { me } = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [passwordOpen, setPasswordOpen] = useState(false);

  const signOut = useMutation({
    mutationFn: logout,
    onSettled: () => {
      void endSession(queryClient);
      router.replace("/login");
    },
  });

  if (!me) return null;
  const { user } = me;
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" aria-label={t("nav.account")} className="gap-1.5">
            <UserRound aria-hidden />
            <span className="hidden max-w-36 truncate sm:inline">{user.display_name}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>
            <span className="block font-medium text-fg">{user.display_name}</span>
            <span className="block text-xs text-fg-muted">
              {user.username} · {t(`roles.${user.role}`)}
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setPasswordOpen(true)}>
            <KeyRound aria-hidden />
            {t("nav.changePassword")}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => signOut.mutate()} disabled={signOut.isPending}>
            <LogOut aria-hidden />
            {t("nav.logout")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />
    </>
  );
}
