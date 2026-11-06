import { type ComponentProps, type ReactNode } from "react";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SectionCardProps extends Omit<ComponentProps<"section">, "title"> {
  title: ReactNode;
  titleId: string;
  aside?: ReactNode;
}

/** Карточка раздела портрета: заголовок h2 связан с секцией через aria-labelledby. */
export function SectionCard({
  title,
  titleId,
  aside,
  className,
  children,
  ...props
}: SectionCardProps) {
  return (
    <section
      aria-labelledby={titleId}
      className={cn("rounded-card border border-border bg-bg", className)}
      {...props}
    >
      <CardHeader className="flex-row items-start justify-between gap-3">
        <CardTitle id={titleId}>{title}</CardTitle>
        {aside}
      </CardHeader>
      <CardContent className="pt-3">{children}</CardContent>
    </section>
  );
}

/** Строка списка как в макете: разделитель сверху, текст слева, значок справа. */
export function Row({ className, ...props }: ComponentProps<"li">) {
  return (
    <li
      className={cn(
        "flex items-start justify-between gap-3 border-t border-border py-3 first:border-t-0 first:pt-0 last:pb-0",
        className,
      )}
      {...props}
    />
  );
}
