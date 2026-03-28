import * as React from "react";
import { cn } from "@/lib/utils";

type BadgeVariant = "default" | "success" | "warning" | "error" | "secondary";

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-blue-600/20 text-blue-400 border-blue-600/30",
  success: "bg-green-600/20 text-green-400 border-green-600/30",
  warning: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
  error: "bg-red-600/20 text-red-400 border-red-600/30",
  secondary: "bg-zinc-700/50 text-zinc-400 border-zinc-600/30",
};

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        variantStyles[variant],
        className,
      )}
      {...props}
    />
  );
}
