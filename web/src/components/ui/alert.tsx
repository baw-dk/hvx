/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva("flex gap-3 rounded-md border p-4 text-[14px] leading-6 [&>svg]:mt-1 [&>svg]:size-4 [&>svg]:shrink-0", {
  variants: {
    tone: {
      info: "border-blueprint/30 bg-blueprint-soft text-blueprint",
      warning: "border-signal/60 bg-signal-soft text-foreground",
      danger: "border-danger/30 bg-danger-soft text-danger",
    },
  },
  defaultVariants: { tone: "info" },
});

export const Alert = ({ className, tone, ...p }: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>) => (
  <div role="status" className={cn(alertVariants({ tone }), className)} {...p} />
);
