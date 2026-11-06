import { ChevronDown } from "lucide-react";
import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * Нативный select в стиле Input — для длинных списков (страны, партнёры): поиск по первым
 * буквам, экранные дикторы и мобильные пикеры работают «из коробки».
 */
export function NativeSelect({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className={cn("relative", className)}>
      <select
        className="h-10 w-full appearance-none rounded-input border border-border bg-bg pr-9 pl-3 text-sm text-fg focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring disabled:opacity-50 aria-invalid:border-error"
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-fg-muted"
        aria-hidden
      />
    </div>
  );
}
