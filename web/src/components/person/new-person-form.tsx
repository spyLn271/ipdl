"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Search } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { Link, useRouter } from "@/i18n/navigation";
import { createPerson } from "@/lib/api/client";
import { countryOptions } from "@/lib/countries";
import { errorMessage } from "@/lib/errors";

export function NewPersonForm() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const queryClient = useQueryClient();
  const countries = useMemo(() => countryOptions(locale), [locale]);
  const [fullName, setFullName] = useState("");
  const [latinName, setLatinName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [citizenship, setCitizenship] = useState("");
  const [context, setContext] = useState("");
  const [touched, setTouched] = useState(false);
  const nameError = touched && fullName.trim().length < 3 ? t("newPerson.fullNameRequired") : null;

  const mutation = useMutation({
    mutationFn: () =>
      createPerson({
        full_name: fullName.trim(),
        latin_name: latinName.trim() || null,
        birth_date: birthDate || null,
        citizenship: citizenship || null,
        context: context.trim() || null,
      }),
    onSuccess: (person) => {
      void queryClient.invalidateQueries({ queryKey: ["persons"] });
      router.push(`/persons/${person.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (fullName.trim().length < 3) return;
    mutation.mutate();
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <Link
        href="/"
        className="inline-flex w-fit items-center gap-1 text-sm text-fg-muted hover:text-fg"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {t("portrait.breadcrumbRegistry")}
      </Link>
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{t("newPerson.title")}</h1>
        <p className="text-sm text-fg-muted">{t("newPerson.subtitle")}</p>
      </div>
      <form
        onSubmit={submit}
        noValidate
        className="flex flex-col gap-5 rounded-card-lg border border-border p-5 sm:p-6"
      >
        <Field
          id="full-name"
          label={t("newPerson.fullName")}
          hint={t("newPerson.fullNameHint")}
          error={nameError}
          required
        >
          <Input
            id="full-name"
            value={fullName}
            maxLength={200}
            autoComplete="off"
            aria-invalid={nameError ? true : undefined}
            aria-describedby={nameError ? "full-name-error" : "full-name-hint"}
            onChange={(e) => setFullName(e.target.value)}
            onBlur={() => setTouched(true)}
            autoFocus
          />
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field id="latin-name" label={t("newPerson.latinName")} hint={t("newPerson.latinHint")}>
            <Input
              id="latin-name"
              value={latinName}
              maxLength={200}
              autoComplete="off"
              aria-describedby="latin-name-hint"
              onChange={(e) => setLatinName(e.target.value)}
            />
          </Field>
          <Field
            id="birth-date"
            label={t("newPerson.birthDate")}
            hint={t("newPerson.birthDateHint")}
          >
            <Input
              id="birth-date"
              type="date"
              value={birthDate}
              min="1900-01-01"
              max={new Date().toISOString().slice(0, 10)}
              aria-describedby="birth-date-hint"
              onChange={(e) => setBirthDate(e.target.value)}
            />
          </Field>
        </div>
        <Field id="citizenship" label={t("newPerson.citizenship")}>
          <NativeSelect
            id="citizenship"
            value={citizenship}
            onChange={(e) => setCitizenship(e.target.value)}
          >
            <option value="">{t("newPerson.citizenshipNone")}</option>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field id="context" label={t("newPerson.context")} hint={t("newPerson.contextHint")}>
          <Textarea
            id="context"
            value={context}
            maxLength={500}
            rows={2}
            aria-describedby="context-hint"
            onChange={(e) => setContext(e.target.value)}
          />
        </Field>
        {mutation.isError && <Alert tone="error">{errorMessage(mutation.error, t)}</Alert>}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-sm text-xs text-fg-muted">{t("newPerson.notice")}</p>
          <Button type="submit" size="lg" disabled={mutation.isPending}>
            <Search aria-hidden />
            {mutation.isPending ? t("newPerson.submitting") : t("newPerson.submit")}
          </Button>
        </div>
      </form>
    </div>
  );
}
