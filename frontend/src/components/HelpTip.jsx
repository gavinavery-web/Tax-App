import React from "react";
import {
  Tooltip as ShadTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";
import { HelpCircle } from "lucide-react";

/**
 * Compact help affordance — a small "?" icon that reveals a one-line
 * explanation on hover or focus. Use sparingly: only next to UI labels a
 * first-time user might find ambiguous (e.g. "Risk level", "Confidence",
 * "Possible match", "Counterparty").
 *
 * Stage 5 polish.
 */
export function HelpTip({ text, side = "top", className = "" }) {
  return (
    <TooltipProvider delayDuration={150}>
      <ShadTooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label="Help"
            className={`inline-flex items-center justify-center text-zinc-400 hover:text-zinc-700 align-middle ${className}`}
            onClick={(e) => e.preventDefault()}
            data-testid="help-tip"
          >
            <HelpCircle className="w-3 h-3" />
          </button>
        </TooltipTrigger>
        <TooltipContent
          side={side}
          className="max-w-xs bg-zinc-900 text-white text-[11px] leading-relaxed"
        >
          {text}
        </TooltipContent>
      </ShadTooltip>
    </TooltipProvider>
  );
}
