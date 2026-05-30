import * as React from "react";
import { useSearchParams } from "react-router";
import type { ModalSize } from "~/components/library/modal/Modal";
import SignInModal from "./modal views/sign in/SignInModal";

type ModalConfig = {
  element: React.ReactNode;
  size?: ModalSize;
  isClosable?: boolean;
  key?: string;
  clearParams?: string[];
};

const normalizeReturnTo = (value: string | null) => {
  if (!value) return "/";
  return value.startsWith("/") ? value : `/${value}`;
};

type ModalFactory = (args: { params: URLSearchParams }) => ModalConfig | null;

// Registry of URL-addressable modals. Extend this with any other modals you want
// to be openable via `?showModal=<id>&...`.
const modalRegistry: Record<string, ModalFactory> = {
  "sign-in": ({ params }) => {
    const returnTo = normalizeReturnTo(params.get("returnTo"));
    return {
      element: <SignInModal returnTo={returnTo} />,
      size: "md",
      isClosable: true,
      key: "redirect-sign-in-modal",
      clearParams: ["returnTo"],
    };
  },
};

type QueryModalSyncProps = {
  openModal: (element: React.ReactNode, size?: ModalSize, isClosable?: boolean, key?: string) => void;
};

export function QueryModalSync({ openModal }: QueryModalSyncProps) {
  const [searchParams, setSearchParams] = useSearchParams();

  React.useEffect(() => {
    const modalId = searchParams.get("showModal");
    if (!modalId) return;

    const cleanParams = (keys: string[]) => {
      if (typeof window === "undefined") return;
      if (keys.length === 0) return;

      const next = new URLSearchParams(searchParams);
      keys.forEach((key) => next.delete(key));
      setSearchParams(next, { replace: true });
    };

    const factory = modalRegistry[modalId];
    if (!factory) return cleanParams(["showModal"]);

    const config = factory({ params: searchParams });
    if (!config) return cleanParams(["showModal"]);

    const { element, size = "md", isClosable = true, key, clearParams = [] } = config;

    openModal(element, size, isClosable, key);

    const keysToClear = new Set<string>(["showModal"]);
    clearParams.forEach((name) => keysToClear.add(name));
    cleanParams(Array.from(keysToClear));
  }, [searchParams, setSearchParams, openModal]);

  return null;
}
