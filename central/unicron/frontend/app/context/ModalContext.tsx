import * as React from "react";
import { ModalRoot, TRANSITION_MS, type ModalSize, type ModalStackItem, type ModalState } from "../components/library/modal/Modal";
import { QueryModalSync } from "../components/QueryModalSync";

export type ModalInjectedProps = {
  closeModal?: () => void;
  modalKey?: string;
  modalState?: ModalState;
};

export type ModalContextType = {
  openModal: (element: React.ReactNode, size?: ModalSize, isClosable?: boolean, key?: string, onOpened?: () => void) => string;
  transitionToModal: (element: React.ReactNode, size?: ModalSize, isClosable?: boolean) => string;
  closeModal: (key?: string) => void;
  _getStackSize: () => number; // synchronous for tests
};

const ModalContext = React.createContext<ModalContextType | null>(null);

/**
 * Supplies modal stack state and helpers to descendant components.
 *
 * @param children React nodes wrapped by the modal context.
 * @returns A context provider that renders the modal stack alongside its children.
 */
export function ModalProvider({ children }: { children: React.ReactNode }) {
  const [stack, setStack] = React.useState<ModalStackItem[]>([]);
  const stackRef = React.useRef<ModalStackItem[]>([]);

  React.useLayoutEffect(() => {
    stackRef.current = stack;
  }, [stack]);

  const setStackSync = React.useCallback((updater: (prev: ModalStackItem[]) => ModalStackItem[]) => {
    setStack((prev) => {
      const next = updater(prev);
      stackRef.current = next;
      return next;
    });
  }, []);

  const closeModal = React.useCallback(
    (key?: string) => {
      setStackSync((prev) => {
        if (prev.length === 0) return prev;
        const idx = key ? prev.findIndex((x) => x.key === key) : prev.length - 1;
        if (idx < 0) return prev;
        const next = [...prev];
        next[idx] = { ...next[idx], modalState: { ...next[idx].modalState, shouldShow: false } };
        const removedKey = next[idx].key;
        setTimeout(() => {
          setStack((curr) => curr.filter((m) => m.key !== removedKey));
          setTimeout(() => {
            stackRef.current = stackRef.current.filter((m) => m.key !== removedKey);
          }, 0);
        }, TRANSITION_MS);
        return next;
      });
    },
    [setStackSync],
  );

  const openModal = React.useCallback<ModalContextType["openModal"]>(
    (component, size = "md", isClosable = true, key, onOpened) => {
      if (key && stackRef.current.some((item) => item.key === key)) return key;
      const k = key ?? Math.random().toString(36).slice(2);
      const item: ModalStackItem = {
        key: k,
        component,
        modalState: { isOpen: true, shouldShow: false, isClosable, size },
      };
      setStackSync((prev) => {
        if (key && prev.some((existing) => existing.key === key)) return prev;
        return [...prev, item];
      });
      requestAnimationFrame(() => {
        setStackSync((prev) => prev.map((m) => (m.key === k ? { ...m, modalState: { ...m.modalState, shouldShow: true } } : m)));
        if (onOpened) setTimeout(onOpened, 0);
      });
      return k;
    },
    [setStackSync],
  );

  const transitionToModal = React.useCallback<ModalContextType["transitionToModal"]>(
    (component, size = "md", isClosable = true) => {
      setStackSync((prev) => {
        if (prev.length === 0) return prev;
        const topIdx = prev.length - 1;
        const next = [...prev];
        next[topIdx] = { ...next[topIdx], modalState: { ...next[topIdx].modalState, shouldShow: false } };
        return next;
      });
      setTimeout(() => {
        setStackSync((prev) => {
          if (prev.length === 0) return prev;
          const topIdx = prev.length - 1;
          const old = prev[topIdx];
          const replaced: ModalStackItem = {
            key: old.key,
            component,
            modalState: { isOpen: true, shouldShow: true, isClosable, size },
          };
          const arr = [...prev];
          arr[topIdx] = replaced;
          return arr;
        });
      }, TRANSITION_MS);
      return stackRef.current.at(-1)?.key ?? "";
    },
    [setStackSync],
  );

  const value: ModalContextType = React.useMemo(
    () => ({
      openModal,
      transitionToModal,
      closeModal,
      _getStackSize: () => stackRef.current.length,
    }),
    [openModal, transitionToModal, closeModal],
  );

  return (
    <ModalContext.Provider value={value}>
      <QueryModalSync openModal={openModal} />
      {children}
      <ModalRoot stack={stack} close={closeModal} />
    </ModalContext.Provider>
  );
}

/**
 * Custom hook to access the modal context.
 *
 * This hook must be used within a `ModalProvider`. If used outside of a `ModalProvider`,
 * it will throw an error.
 *
 * @returns The current modal context value.
 * @throws {Error} If the hook is used outside of a `ModalProvider`.
 */
export function useModal(): ModalContextType {
  const context = React.useContext(ModalContext);
  if (!context) throw new Error("ModalContextType must be used within ModalProvider");

  return context;
}
