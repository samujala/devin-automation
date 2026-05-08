import * as React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "destructive" | "outline" | "blue" | "green" | "amber" | "slate" | "merged";
}

const variantClasses: Record<string, string> = {
  default: "bg-[var(--primary)] text-[var(--primary-foreground)]",
  success: "bg-emerald-600 text-white dark:bg-emerald-500",
  destructive: "bg-red-600 text-white dark:bg-red-500",
  outline: "border border-[var(--border)] text-[var(--foreground)]",
  blue: "bg-blue-600 text-white dark:bg-blue-500",
  green: "bg-emerald-600 text-white dark:bg-emerald-500",
  amber: "bg-amber-500 text-white",
  slate: "bg-slate-500 text-white",
  merged: "bg-indigo-600 text-white dark:bg-indigo-500",
};

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = "default", ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        variantClasses[variant] ?? variantClasses.default,
        className
      )}
      {...props}
    />
  )
);
Badge.displayName = "Badge";

export { Badge };
