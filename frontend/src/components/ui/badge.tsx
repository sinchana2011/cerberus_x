import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300",
        info: "border-blue-400/30 bg-blue-500/15 text-blue-300",
        purple: "border-purple-400/30 bg-purple-500/15 text-purple-300",
        success: "border-emerald-400/30 bg-emerald-500/15 text-emerald-300",
        warning: "border-amber-400/30 bg-amber-500/15 text-amber-300",
        danger: "border-rose-400/30 bg-rose-500/15 text-rose-300",
        neutral: "border-slate-700 bg-slate-800/70 text-slate-300",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
