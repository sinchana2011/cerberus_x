import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C87620]/45 disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        default:
          "bg-[#C87620] text-white font-semibold hover:bg-[#B2671A] shadow-sm shadow-[#292820]/10",
        secondary:
          "bg-[#F6F5F0] text-[#292820] border border-[#E8E4DA] hover:bg-[#ECE8DE]",
        outline:
          "border border-[#E8E4DA] bg-white text-[#292820] hover:border-[#D9B98C] hover:bg-[#F6F5F0]",
        ghost:
          "text-[#77736A] hover:bg-[#EFECE4] hover:text-[#292820]",
        destructive:
          "bg-[#C65D50] text-white hover:bg-[#B35044] border border-[#C65D50]",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-[10px] px-3 text-xs",
        lg: "h-10 rounded-xl px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
