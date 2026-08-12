import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import RegisterDatasetDialog from "@/components/datasets/register-dataset-dialog";
import { ApiError } from "@/lib/api";

async function openDialog(onRegister: (path: string, name: string) => Promise<void>) {
  render(<RegisterDatasetDialog onRegister={onRegister} />);
  await userEvent.click(screen.getByRole("button", { name: "Register sequence" }));
}

describe("RegisterDatasetDialog", () => {
  it("refuses an empty path without calling the server", async () => {
    const onRegister = vi.fn();
    await openDialog(onRegister);
    await userEvent.click(screen.getByRole("button", { name: /^Register$/ }));

    expect(screen.getByRole("alert")).toHaveTextContent("Enter the path");
    expect(onRegister).not.toHaveBeenCalled();
  });

  it("passes the trimmed path and name through", async () => {
    const onRegister = vi.fn().mockResolvedValue(undefined);
    await openDialog(onRegister);
    await userEvent.type(screen.getByLabelText("Path"), "  /data/room1  ");
    await userEvent.type(screen.getByLabelText("Name"), "  room one  ");
    await userEvent.click(screen.getByRole("button", { name: /^Register$/ }));

    expect(onRegister).toHaveBeenCalledWith("/data/room1", "room one");
  });

  it("surfaces the server message when the folder is not a sequence", async () => {
    const onRegister = vi
      .fn()
      .mockRejectedValue(
        new ApiError(400, { code: "sequence_unreadable", message: "missing mav0/cam0/data.csv" }),
      );
    await openDialog(onRegister);
    await userEvent.type(screen.getByLabelText("Path"), "/data/empty");
    await userEvent.click(screen.getByRole("button", { name: /^Register$/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("missing mav0/cam0/data.csv");
  });

  it("keeps the dialog open on failure so the path can be corrected", async () => {
    const onRegister = vi
      .fn()
      .mockRejectedValue(
        new ApiError(409, { code: "path_already_registered", message: "Already registered." }),
      );
    await openDialog(onRegister);
    await userEvent.type(screen.getByLabelText("Path"), "/data/room1");
    await userEvent.click(screen.getByRole("button", { name: /^Register$/ }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("Path")).toHaveValue("/data/room1");
  });
});
