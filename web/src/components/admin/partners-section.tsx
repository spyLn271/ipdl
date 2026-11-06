"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { createPartner, listPartners, updatePartner } from "@/lib/api/client";
import { type Partner } from "@/lib/api/schemas";
import { countryName, countryOptions } from "@/lib/countries";
import { errorMessage } from "@/lib/errors";

export function PartnersSection() {
  const t = useTranslations();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const countries = useMemo(() => countryOptions(locale), [locale]);
  const partners = useQuery({ queryKey: ["partners"], queryFn: listPartners });
  const [country, setCountry] = useState("");
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");

  const create = useMutation({
    mutationFn: () =>
      createPartner({ country, name: name.trim(), contact: contact.trim() || null }),
    onSuccess: () => {
      setName("");
      setContact("");
      void queryClient.invalidateQueries({ queryKey: ["partners"] });
    },
  });
  const toggle = useMutation({
    mutationFn: (partner: Partner) => updatePartner(partner.id, { is_active: !partner.is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["partners"] }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!country || name.trim().length < 2) return;
    create.mutate();
  }

  return (
    <section aria-labelledby="admin-partners" className="flex flex-col gap-3">
      <h2 id="admin-partners" className="text-lg font-semibold text-fg">
        {t("admin.partners")}
      </h2>
      <form
        onSubmit={submit}
        className="grid gap-3 rounded-card border border-border p-4 md:grid-cols-[14rem_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end"
      >
        <Field id="p-country" label={t("admin.country")} required>
          <NativeSelect
            id="p-country"
            value={country}
            required
            onChange={(e) => setCountry(e.target.value)}
          >
            <option value="" disabled>
              {t("newPerson.citizenshipNone")}
            </option>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field id="p-name" label={t("admin.name")} required>
          <Input
            id="p-name"
            value={name}
            minLength={2}
            maxLength={200}
            required
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field id="p-contact" label={t("admin.contact")}>
          <Input
            id="p-contact"
            value={contact}
            maxLength={1000}
            onChange={(e) => setContact(e.target.value)}
          />
        </Field>
        <Button type="submit" disabled={create.isPending || !country || name.trim().length < 2}>
          <Plus aria-hidden />
          {t("admin.createPartner")}
        </Button>
      </form>
      {(create.isError || toggle.isError) && (
        <Alert tone="error">{errorMessage(create.error ?? toggle.error, t)}</Alert>
      )}
      {partners.isPending ? (
        <Skeleton className="h-32" />
      ) : partners.isError ? (
        <Alert tone="error">{errorMessage(partners.error, t)}</Alert>
      ) : (
        <ul className="divide-y divide-border rounded-card border border-border">
          {partners.data.map((partner) => (
            <li
              key={partner.id}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
            >
              <span className="min-w-0">
                <span className="block text-sm font-medium text-fg">{partner.name}</span>
                <span className="block text-xs text-fg-muted">
                  {countryName(partner.country, locale)}
                  {partner.contact && ` · ${partner.contact}`}
                </span>
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={partner.is_active ? "ok" : "neutral"}>
                  {partner.is_active ? t("admin.active") : t("admin.inactive")}
                </Badge>
                <Button
                  size="sm"
                  variant={partner.is_active ? "danger" : "secondary"}
                  disabled={toggle.isPending}
                  onClick={() => toggle.mutate(partner)}
                >
                  {partner.is_active ? t("admin.deactivate") : t("admin.activate")}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
