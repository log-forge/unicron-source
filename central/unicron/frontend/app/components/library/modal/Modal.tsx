import React from "react";
import { ModalOverlay, Modal as RaModal, Dialog, Heading } from "react-aria-components";
import { X } from "lucide-react";
import { Button } from "../buttons/Button";

// Modal sizing tokens – mapped to width utilities; uses existing Tailwind/token classes.
export type ModalSize = "xxsm" | "xsm" | "sm" | "md" | "lg" | "xl" | "full" | "static_md" | "static_lg";

export type ModalState = {
  isOpen: boolean;
  shouldShow: boolean; // enter/exit animation state
  isClosable: boolean;
  size: ModalSize;
};

export type ModalStackItem = {
  key: string;
  component: React.ReactNode;
  modalState: ModalState;
};

export const TRANSITION_MS = 220;
export const PADDING = { x: "px-md", y: "py-md" };
export const RADIUS = "rounded-md";

const sizeToClass: Record<ModalSize, string> = {
  xxsm: "w-[min(90vw,340px)]",
  xsm: "w-[min(90vw,446px)]",
  sm: "w-[min(90vw,528px)]",
  md: "w-[min(90vw,620px)]",
  lg: "w-[min(90vw,792px)]",
  xl: "w-[min(90vw,990px)]",
  full: "w-[100vw] h-[100vh] !rounded-none",
  // static_* variants: fixed max width but allow narrowing below token on very small viewports
  static_md: "w-[min(90vw,620px)]",
  static_lg: "w-[min(90vw,792px)]",
};

export function ModalRoot({ stack, close }: { stack: ModalStackItem[]; close: (key?: string) => void }) {
  if (stack.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-[200]">
      {stack.map((item, i) => {
        const { modalState } = item;
        const zBase = 1000 + i * 2;
        const isTop = i === stack.length - 1;

        return (
          <ModalOverlay
            key={item.key}
            isOpen={modalState.isOpen}
            isDismissable={modalState.isClosable}
            isKeyboardDismissDisabled={!modalState.isClosable}
            onOpenChange={(open) => {
              if (!open && modalState.isClosable) close(item.key);
            }}
            className={`fixed inset-0 grid place-items-center bg-[var(--overlay,rgba(0,0,0,0.55))] backdrop-blur-sm transition-opacity ${
              modalState.shouldShow ? "pointer-events-auto" : "pointer-events-none"
            }`}
            style={{ zIndex: zBase, opacity: modalState.shouldShow ? 1 : 0 }}
          >
            <RaModal className="outline-none">
              <Dialog
                aria-label="Modal"
                className={[
                  "relative max-h-[100vh] overflow-hidden bg-background text-text",
                  `${RADIUS} border border-neutral/20 shadow-xl shadow-secondary/10`,
                  "transform transition-all",
                  modalState.shouldShow ? "translate-y-0 scale-100 opacity-100" : "translate-y-6 scale-95 opacity-0",
                  sizeToClass[modalState.size],
                ].join(" ")}
                style={{ transitionDuration: `${TRANSITION_MS}ms` }}
                onClick={(e) => e.stopPropagation()}
              >
                <Heading slot="title" className="sr-only">
                  Dialog
                </Heading>
                {isTop && modalState.isClosable && (
                  <Button
                    aria-label="Close"
                    variant="glass"
                    tone="secondary"
                    radius="sm"
                    padding="4xs"
                    textSize="base"
                    className="absolute! top-3xs right-3xs flex aspect-square h-sm w-sm items-center justify-center border border-divider bg-foreground/80 !p-0 backdrop-blur transition hover:bg-foreground"
                    onPress={() => close(item.key)}
                  >
                    <X className="h-sm w-sm" strokeWidth={2} aria-hidden="true" />
                  </Button>
                )}
                {/* Close button only on top-most injected by consumer (we don't know top here so consumer logic handles) */}
                <div className={`max-h-screen max-w-full overflow-auto ${PADDING.x} ${PADDING.y}`}>
                  <div className="h-full w-full">
                    <div>
                      {React.Children.map(item.component, (child) => {
                        if (React.isValidElement(child)) {
                          return React.cloneElement(child as React.ReactElement<any>, {
                            ...(child.props as object),
                            modalState: item.modalState,
                            modalKey: item.key,
                            closeModal: () => close(item.key),
                          });
                        }
                        return child;
                      })}
                    </div>
                  </div>
                </div>
              </Dialog>
            </RaModal>
          </ModalOverlay>
        );
      })}
    </div>
  );
}
