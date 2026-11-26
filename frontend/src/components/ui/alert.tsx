import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative w-full rounded-xl border px-4 py-3 text-sm flex items-start gap-3",
  {
    variants: {
      variant: {
        info: "border-cyan-500/30 bg-cyan-500/10 text-cyan-100",
        success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-100",
        warning: "border-amber-500/30 bg-amber-500/10 text-amber-100",
        destructive: "border-rose-500/35 bg-rose-500/10 text-rose-100",
      },
    },
    defaultVariants: {
      variant: "info",
    },
  }
);

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

export function Alert({ className, variant, ...props }: AlertProps) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}
