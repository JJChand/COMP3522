"""Execute the notebook with IPython in process when local kernel ports are unavailable."""
from pathlib import Path
import warnings

from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output
import nbformat

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "research/task1_three_family_representation.ipynb"


if __name__ == "__main__":
    notebook = nbformat.read(PATH, as_version=4)
    shell = InteractiveShell.instance()
    warnings.filterwarnings("ignore", message="The 'generic' unit for NumPy timedelta is deprecated.*", category=DeprecationWarning)
    count = 0
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        count += 1
        with capture_output() as captured:
            result = shell.run_cell(cell.source, store_history=False)
        cell.execution_count = count
        cell.outputs = []
        if captured.stdout:
            cell.outputs.append(nbformat.v4.new_output("stream", name="stdout", text=captured.stdout))
        if captured.stderr:
            cell.outputs.append(nbformat.v4.new_output("stream", name="stderr", text=captured.stderr))
        for rich in captured.outputs:
            cell.outputs.append(nbformat.v4.new_output("display_data", data=rich.data, metadata=rich.metadata))
        error = result.error_before_exec or result.error_in_exec
        if error:
            cell.outputs.append(nbformat.v4.new_output("error", ename=type(error).__name__, evalue=str(error), traceback=[]))
        notebook.metadata["execution_backend"] = "IPython InteractiveShell, sequential in-process cells"
        nbformat.validate(notebook)
        nbformat.write(notebook, PATH)
        print(f"Executed cell {index+1}/{len(notebook.cells)}", flush=True)
        if error:
            raise error
    print(f"Saved {PATH}", flush=True)
