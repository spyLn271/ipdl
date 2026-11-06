"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { Badge } from "@/components/ui/badge";
import { NativeSelect } from "@/components/ui/native-select";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { updateRequest } from "@/lib/api/client";
import { type ExchangeRequest, REQUEST_STATUSES, type RequestStatus } from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";

const STATUS_TONE = { open: "info", in_progress: "warning", closed: "neutral" } as const;

export function RequestLogCard({
  personId,
  requests,
  canEdit,
}: {
  personId: string;
  requests: readonly ExchangeRequest[];
  canEdit: boolean;
}) {
  const t = useTranslations();
  const format = useFormatter();
  const locale = useLocale();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: RequestStatus }) =>
      updateRequest(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["person", personId] }),
  });

  return (
    <SectionCard title={t("portrait.requestsTitle")} titleId="requests-title">
      {requests.length === 0 ? (
        <p className="text-sm text-fg-muted">{t("portrait.requestsEmpty")}</p>
      ) : (
        <ul>
          {requests.map((request) => {
            const Icon = request.direction === "incoming" ? ArrowDownLeft : ArrowUpRight;
            const editable = canEdit && request.kind !== "disclosure";
            return (
              <Row key={request.id} className="flex-col items-stretch gap-2">
                <div className="flex min-w-0 gap-2">
                  <Icon
                    className="mt-0.5 size-4 shrink-0 text-fg-muted"
                    aria-label={t(`requests.direction.${request.direction}`)}
                  />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-sm font-medium text-fg">
                      {countryName(request.partner.country, locale)} · {request.partner.name}
                    </span>
                    <span className="text-xs text-fg-muted">
                      {format.dateTime(new Date(request.created_at), { dateStyle: "short" })} ·{" "}
                      {t(`requests.kind.${request.kind}`)}
                    </span>
                    <span className="text-xs text-fg">{request.purpose}</span>
                    {request.legal_basis && (
                      <span className="text-xs text-fg-muted">{request.legal_basis}</span>
                    )}
                  </div>
                </div>
                {editable ? (
                  <NativeSelect
                    aria-label={t("portrait.changeStatus")}
                    className="ml-6 w-40"
                    value={request.status}
                    disabled={mutation.isPending}
                    onChange={(e) =>
                      mutation.mutate({ id: request.id, status: e.target.value as RequestStatus })
                    }
                  >
                    {REQUEST_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {t(`requests.status.${status}`)}
                      </option>
                    ))}
                  </NativeSelect>
                ) : (
                  <Badge tone={STATUS_TONE[request.status]} className="ml-6 w-fit">
                    {request.kind === "disclosure"
                      ? t("requests.kind.disclosure")
                      : t(`requests.status.${request.status}`)}
                  </Badge>
                )}
              </Row>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}
