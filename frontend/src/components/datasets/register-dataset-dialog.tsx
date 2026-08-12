"use client";

import { type FC, type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";

interface RegisterDatasetDialogProps {
  onRegister: (path: string, name: string) => Promise<void>;
}

const RegisterDatasetDialog: FC<RegisterDatasetDialogProps> = ({ onRegister }) => {
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function reset() {
    setPath("");
    setName("");
    setError(null);
    setFieldError(null);
    setPending(false);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!path.trim()) {
      setError("Enter the path to the sequence folder.");
      setFieldError("path");
      return;
    }
    setError(null);
    setFieldError(null);
    setPending(true);
    try {
      await onRegister(path.trim(), name.trim());
      reset();
      setOpen(false);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not register that sequence.");
      setFieldError(caught instanceof ApiError ? (caught.field ?? null) : null);
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">Register sequence</Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Register a sequence</DialogTitle>
            <DialogDescription>
              Point at the folder holding <span className="font-mono">mav0</span>. The files stay
              where they are; driftline records what it finds.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="dataset-path">Path</Label>
              <Input
                id="dataset-path"
                value={path}
                onChange={(event) => setPath(event.target.value)}
                placeholder="/data/dataset-room1_512_16"
                aria-invalid={fieldError === "path"}
                autoComplete="off"
                spellCheck={false}
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="dataset-name">Name</Label>
              <Input
                id="dataset-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Defaults to the folder name"
                autoComplete="off"
              />
            </div>

            {error ? (
              <p role="alert" className="text-destructive text-sm">
                {error}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? "Reading sequence" : "Register"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default RegisterDatasetDialog;
