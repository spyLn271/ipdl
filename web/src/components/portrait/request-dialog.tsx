"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
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
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { createRequest, listPartners } from "@/lib/api/client";
import { type RequestKind } from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";
import { errorMessage } from "@/lib/errors";

interface RequestDialogProps {
  personId: string;
  kind: RequestKind;
  /** Пользователь-партнёр: запрос уходит от его ПФР, выбирать партнёра не нужно */
  partnerId?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RequestDialog({
  personId,
  kind,
  partnerId,
  open,
  onOpenChange,
}: RequestDialogProps) {
  const t = useTranslations();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const isPartner = Boolean(partnerId);
  const partners = useQuery({
    queryKey: ["partners"],
    queryFn: listPartners,
    enabled: open && !isPartner,
  });
  const [partner, setPartner] = useState("");
  const [purpose, setPurpose] = useState("");
  const [legalBasis, setLegalBasis] = useState("");
  const disclose = kind === "disclosure";
  const active = (partners.data ?? []).filter((p) => p.is_active);

  const mutation = useMutation({
    mutationFn: () =>
      createRequest(personId, {
        partner_id: partnerId ?? partner,
        kind,
        direction: isPartner ? "incoming" : "outgoing",
        purpose: purpose.trim(),
        legal_basis: legalBasis.trim() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["person", personId] });
      setPurpose("");
      setLegalBasis("");
      onOpenChange(false);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if ((!partnerId && !partner) || purpose.trim().length < 3) return;
    mutation.mutate();
  }

  const titleKey = disclose ? "discloseTitle" : "infoTitle";
  const descriptionKey = disclose
    ? "discloseDescription"
    : isPartner
      ? "partnerInfoDescription"
      : "infoDescription";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <form onSubmit={submit} className="flex min-h-0 flex-col">
          <DialogHeader>
            <DialogTitle>{t(`requestDialog.${titleKey}`)}</DialogTitle>
            <DialogDescription>{t(`requestDialog.${descriptionKey}`)}</DialogDescription>
          </DialogHeader>
          <DialogBody>
            {!isPartner && (
              <Field id="request-partner" label={t("requestDialog.partner")} required>
                {partners.isSuccess && active.length === 0 ? (
                  <Alert tone="warning">{t("requestDialog.noPartners")}</Alert>
                ) : (
                  <NativeSelect
                    id="request-partner"
                    value={partner}
                    required
                    onChange={(e) => setPartner(e.target.value)}
                  >
                    <option value="" disabled>
                      {t("requestDialog.partnerPlaceholder")}
                    </option>
                    {active.map((p) => (
                      <option key={p.id} value={p.id}>
                        {countryName(p.country, locale)} · {p.name}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            )}
            <Field
              id="request-purpose"
              label={t("requestDialog.purpose")}
              hint={t("requestDialog.purposeHint")}
              required
            >
              <Textarea
                id="request-purpose"
                value={purpose}
                minLength={3}
                maxLength={2000}
                rows={3}
                required
                aria-describedby="request-purpose-hint"
                onChange={(e) => setPurpose(e.target.value)}
              />
            </Field>
            {disclose && (
              <Field
                id="request-basis"
                label={t("requestDialog.legalBasis")}
                hint={t("requestDialog.legalBasisHint")}
              >
                <Textarea
                  id="request-basis"
                  value={legalBasis}
                  maxLength={1000}
                  rows={2}
                  aria-describedby="request-basis-hint"
                  onChange={(e) => setLegalBasis(e.target.value)}
                />
              </Field>
            )}
            {mutation.isError && <Alert tone="error">{errorMessage(mutation.error, t)}</Alert>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={mutation.isPending || (!partnerId && !partner) || purpose.trim().length < 3}
            >
              {disclose ? t("requestDialog.submitDisclose") : t("requestDialog.submitInfo")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
