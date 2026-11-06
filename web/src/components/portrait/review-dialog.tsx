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
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { type ReviewInput, saveReview } from "@/lib/api/client";
import {
  type FactorKey,
  PEP_CATEGORIES,
  PEP_TENURES,
  type PepCategory,
  type PepTenure,
  type Portrait,
  type Review,
  RISK_LEVELS,
  type RiskLevel,
  type Verification,
  VERIFICATIONS,
} from "@/lib/api/schemas";
import { errorMessage } from "@/lib/errors";

interface FactorDraft {
  level: RiskLevel | "";
  comment: string;
}

interface ReviewDialogProps {
  personId: string;
  portraitId: string;
  portrait: Portrait;
  review: Review | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Факторы, у которых аналитик выбрал уровень, — без обоснования сохранить нельзя. */
export function missingComments(factors: Partial<Record<FactorKey, FactorDraft>>): FactorKey[] {
  return (Object.entries(factors) as [FactorKey, FactorDraft][])
    .filter(([, draft]) => draft.level !== "" && draft.comment.trim().length < 3)
    .map(([key]) => key);
}

export function ReviewDialog({
  personId,
  portraitId,
  portrait,
  review,
  open,
  onOpenChange,
}: ReviewDialogProps) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const [pepCategory, setPepCategory] = useState<PepCategory | "">(review?.pep_category ?? "");
  const [pepTenure, setPepTenure] = useState<PepTenure | "">(review?.pep_tenure ?? "");
  const [pepComment, setPepComment] = useState(review?.pep_comment ?? "");
  const [conclusion, setConclusion] = useState(review?.conclusion ?? "");
  const [factors, setFactors] = useState<Partial<Record<FactorKey, FactorDraft>>>(() =>
    Object.fromEntries(
      portrait.risk.factors.map((f) => [
        f.key,
        {
          level: review?.factors[f.key]?.level ?? "",
          comment: review?.factors[f.key]?.comment ?? "",
        },
      ]),
    ),
  );
  const [sources, setSources] = useState<Record<string, Verification>>(() => ({
    ...Object.fromEntries(portrait.sources.map((s) => [s.id, s.verification])),
    ...review?.sources,
  }));
  const [submitted, setSubmitted] = useState(false);
  const missing = missingComments(factors);
  const reviewable = portrait.sources.filter((s) => s.analyzed || s.facts > 0 || s.fetched);

  const mutation = useMutation({
    mutationFn: () => {
      const input: ReviewInput = {
        pep_category: pepCategory || null,
        pep_tenure: pepTenure || null,
        pep_comment: pepComment.trim() || null,
        conclusion: conclusion.trim() || null,
        factors: Object.fromEntries(
          (Object.entries(factors) as [FactorKey, FactorDraft][])
            .filter(([, d]) => d.level !== "")
            .map(([key, d]) => [key, { level: d.level as RiskLevel, comment: d.comment.trim() }]),
        ),
        // В решение попадают только изменённые аналитиком статусы
        sources: Object.fromEntries(Object.entries(sources).filter(([, v]) => v !== "unverified")),
      };
      return saveReview(portraitId, input);
    },
    onSuccess: (out) => {
      queryClient.setQueryData(["portrait", portraitId], out);
      void queryClient.invalidateQueries({ queryKey: ["person", personId] });
      void queryClient.invalidateQueries({ queryKey: ["persons"] });
      onOpenChange(false);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (missing.length > 0) return;
    mutation.mutate();
  }

  function setFactor(key: FactorKey, patch: Partial<FactorDraft>) {
    setFactors((prev) => ({ ...prev, [key]: { level: "", comment: "", ...prev[key], ...patch } }));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")} className="max-w-3xl">
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogHeader>
            <DialogTitle>{t("review.title")}</DialogTitle>
            <DialogDescription>{t("review.description")}</DialogDescription>
          </DialogHeader>
          <DialogBody className="gap-6">
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-2 text-sm font-semibold text-fg">
                {t("review.pepSection")}
              </legend>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field id="review-pep" label={t("review.pepCategory")}>
                  <NativeSelect
                    id="review-pep"
                    value={pepCategory}
                    onChange={(e) => setPepCategory(e.target.value as PepCategory | "")}
                  >
                    <option value="">
                      {t("review.keepAuto")} ({t(`pep.${portrait.pep.category}`)})
                    </option>
                    {PEP_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {t(`pepLong.${c}`)}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field id="review-tenure" label={t("review.pepTenure")}>
                  <NativeSelect
                    id="review-tenure"
                    value={pepTenure}
                    onChange={(e) => setPepTenure(e.target.value as PepTenure | "")}
                  >
                    <option value="">
                      {t("review.keepAuto")} ({t(`tenure.${portrait.pep.tenure}`)})
                    </option>
                    {PEP_TENURES.map((v) => (
                      <option key={v} value={v}>
                        {t(`tenure.${v}`)}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              </div>
              <Field id="review-pep-comment" label={t("review.pepComment")}>
                <Textarea
                  id="review-pep-comment"
                  rows={2}
                  maxLength={2000}
                  value={pepComment}
                  onChange={(e) => setPepComment(e.target.value)}
                />
              </Field>
            </fieldset>

            <fieldset className="flex flex-col gap-1">
              <legend className="mb-2 text-sm font-semibold text-fg">
                {t("review.factorsSection")}
              </legend>
              {portrait.risk.factors.map((factor) => {
                const draft = factors[factor.key] ?? { level: "", comment: "" };
                const invalid = submitted && missing.includes(factor.key);
                const id = `review-factor-${factor.key}`;
                return (
                  <div
                    key={factor.key}
                    className="grid gap-2 border-t border-border py-3 first-of-type:border-t-0 sm:grid-cols-[minmax(0,14rem)_10rem_minmax(0,1fr)] sm:items-start"
                  >
                    <label htmlFor={id} className="text-sm text-fg">
                      {t(`factors.${factor.key}`)}
                      <span className="block text-xs text-fg-muted">
                        {t("review.factorAuto", { level: t(`levels.${factor.auto_level}`) })}
                      </span>
                    </label>
                    <NativeSelect
                      id={id}
                      value={draft.level}
                      onChange={(e) =>
                        setFactor(factor.key, { level: e.target.value as RiskLevel | "" })
                      }
                    >
                      <option value="">{t("review.keepAuto")}</option>
                      {RISK_LEVELS.map((level) => (
                        <option key={level} value={level}>
                          {t(`levels.${level}`)}
                        </option>
                      ))}
                    </NativeSelect>
                    <div className="flex flex-col gap-1">
                      <Input
                        aria-label={`${t("review.factorComment")}: ${t(`factors.${factor.key}`)}`}
                        placeholder={t("review.factorComment")}
                        value={draft.comment}
                        maxLength={1000}
                        disabled={draft.level === ""}
                        aria-invalid={invalid || undefined}
                        aria-describedby={invalid ? `${id}-error` : undefined}
                        onChange={(e) => setFactor(factor.key, { comment: e.target.value })}
                      />
                      {invalid && (
                        <p id={`${id}-error`} className="text-xs text-error-fg" role="alert">
                          {t("review.commentRequired")}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </fieldset>

            <Field
              id="review-conclusion"
              label={t("review.conclusion")}
              hint={t("review.conclusionHint")}
            >
              <Textarea
                id="review-conclusion"
                rows={4}
                maxLength={5000}
                value={conclusion}
                aria-describedby="review-conclusion-hint"
                onChange={(e) => setConclusion(e.target.value)}
              />
            </Field>

            {reviewable.length > 0 && (
              <fieldset className="flex flex-col gap-1">
                <legend className="mb-2 text-sm font-semibold text-fg">
                  {t("review.sourcesSection")}
                </legend>
                {reviewable.map((source) => (
                  <div
                    key={source.id}
                    className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-2 first-of-type:border-t-0"
                  >
                    <label
                      htmlFor={`review-source-${source.id}`}
                      className="min-w-0 flex-1 text-sm text-fg"
                    >
                      <span className="mr-1.5 font-mono text-xs text-fg-muted">{source.id}</span>
                      {source.title}
                      <span className="block text-xs text-fg-muted">{source.domain}</span>
                    </label>
                    <NativeSelect
                      id={`review-source-${source.id}`}
                      className="w-40"
                      value={sources[source.id] ?? "unverified"}
                      onChange={(e) =>
                        setSources((prev) => ({
                          ...prev,
                          [source.id]: e.target.value as Verification,
                        }))
                      }
                    >
                      {VERIFICATIONS.map((v) => (
                        <option key={v} value={v}>
                          {t(`verifications.${v}`)}
                        </option>
                      ))}
                    </NativeSelect>
                  </div>
                ))}
              </fieldset>
            )}
            {mutation.isError && <Alert tone="error">{errorMessage(mutation.error, t)}</Alert>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? t("common.saving") : t("review.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
