import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative w-full rounded-xl border px-4 py-3 text-sm flex items-start gap-3",
  {
    variants: {
      variant: {
        info: "border-[#D9B98C] bg-[#FAF6EE] text-[#292820]",
        success: "border-[#638568]/35 bg-[#638568]/10 text-[#292820]",
        warning: "border-[#D49A45]/45 bg-[#D49A45]/10 text-[#292820]",
        destructive: "border-[#C65D50]/45 bg-[#C65D50]/10 text-[#8F372D]",
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
