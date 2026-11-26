import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-[#C87620]/30 bg-[#C87620]/10 text-[#A85F15]",
        info: "border-[#D9B98C] bg-[#D9B98C]/25 text-[#292820]",
        purple: "border-[#D9B98C] bg-[#F6F5F0] text-[#7A5226]",
        success: "border-[#638568]/35 bg-[#638568]/12 text-[#48664D]",
        warning: "border-[#D49A45]/40 bg-[#D49A45]/15 text-[#94661F]",
        danger: "border-[#C65D50]/35 bg-[#C65D50]/12 text-[#A6463B]",
        neutral: "border-[#E8E4DA] bg-[#F6F5F0] text-[#77736A]",
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
