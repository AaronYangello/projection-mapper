import { useEffect, useId, useRef } from "react";

export function useUnsavedWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
}

export function DiscardDialog({
  open,
  title,
  description,
  onKeep,
  onDiscard,
}: {
  open: boolean;
  title: string;
  description: string;
  onKeep: () => void;
  onDiscard: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId(),
    descriptionId = useId();
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        onKeep();
      }}
    >
      <h2 id={titleId}>{title}</h2>
      <p id={descriptionId}>{description}</p>
      <div className="dialog-actions">
        <button autoFocus onClick={onKeep}>
          Keep editing
        </button>
        <button className="danger-button" onClick={onDiscard}>
          Discard changes
        </button>
      </div>
    </dialog>
  );
}
