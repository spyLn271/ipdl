"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { listAudit } from "@/lib/api/client";
import { errorMessage } from "@/lib/errors";

const PAGE_SIZE = 25;

function details(value: Record<string, unknown> | null): string {
  if (!value) return "";
  return Object.entries(value)
    .map(([key, v]) => `${key}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

export function AuditSection() {
  const t = useTranslations();
  const format = useFormatter();
  const [action, setAction] = useState("");
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["audit", { applied, page }],
    queryFn: () => listAudit({ action: applied || undefined, page, pageSize: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });
  const pages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  return (
    <section aria-labelledby="admin-audit" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="admin-audit" className="text-lg font-semibold text-fg">
          {t("admin.audit")}
        </h2>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(action.trim());
            setPage(1);
          }}
        >
          <label htmlFor="audit-action" className="sr-only">
            {t("admin.actionFilter")}
          </label>
          <Input
            id="audit-action"
            className="w-64"
            placeholder={t("admin.actionPlaceholder")}
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
          <Button type="submit" variant="secondary">
            {t("admin.actionFilter")}
          </Button>
        </form>
      </div>
      {query.isPending ? (
        <Skeleton className="h-64" />
      ) : query.isError ? (
        <Alert tone="error">{errorMessage(query.error, t)}</Alert>
      ) : (
        <>
          <div className="overflow-x-auto rounded-card border border-border">
            <table className="w-full min-w-[52rem] text-left text-xs">
              <thead className="border-b border-border bg-bg-subtle">
                <tr>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    {t("admin.auditTime")}
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    {t("admin.auditUser")}
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    {t("admin.auditAction")}
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    {t("admin.auditObject")}
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    {t("admin.auditIp")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {query.data.items.map((event) => (
                  <tr key={event.id} className="align-top">
                    <td className="px-3 py-2 font-mono whitespace-nowrap">
                      {format.dateTime(new Date(event.at), {
                        dateStyle: "short",
                        timeStyle: "medium",
                      })}
                    </td>
                    <td className="px-3 py-2">{event.username ?? t("admin.system")}</td>
                    <td className="px-3 py-2 font-mono text-fg">{event.action}</td>
                    <td className="max-w-md px-3 py-2 text-fg-muted">
                      {event.object_type && (
                        <span className="font-mono">
                          {event.object_type}:{event.object_id?.slice(0, 8)}{" "}
                        </span>
                      )}
                      <span className="break-words">{details(event.details)}</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-fg-muted">{event.ip ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <nav className="flex items-center justify-between" aria-label="pagination">
              <Button
                size="sm"
                variant="secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                {t("common.prev")}
              </Button>
              <span className="text-sm text-fg-muted">{t("common.pageOf", { page, pages })}</span>
              <Button
                size="sm"
                variant="secondary"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t("common.next")}
              </Button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
