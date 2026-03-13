import os
import sys


def process_frd_file(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find the empty line separating metadata and CSV
    try:
        sep_idx = lines.index("\n")
    except ValueError:
        sep_idx = lines.index("\r\n") if "\r\n" in lines else -1
    if sep_idx == -1:
        raise ValueError(f"No empty line found in {input_path}")

    metadata = lines[:sep_idx]
    csv_lines = lines[sep_idx + 1 :]
    if len(csv_lines) < 2:
        raise ValueError(f"CSV section missing or incomplete in {input_path}")

    header = csv_lines[0].rstrip("\r\n").split(",")
    data_rows = [line.rstrip("\r\n").split(",") for line in csv_lines[1:]]

    if len(header) < 2:
        raise ValueError(f"CSV header too short in {input_path}")
    for row in data_rows:
        if len(row) != len(header):
            raise ValueError(f"CSV header/data mismatch in {input_path}")

    # Move last column after first
    def move_last_after_first(row):
        return [row[0], row[-1]] + row[1:-1]

    new_header = move_last_after_first(header)
    new_data_rows = [move_last_after_first(row) for row in data_rows]

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(metadata)
        f.write("\n")
        f.write(",".join(new_header) + "\n")
        for row in new_data_rows:
            f.write(",".join(row) + "\n")


def main():
    if len(sys.argv) != 3:
        print("Usage: python mix_column_frd <input_folder> <output_folder>")
        sys.exit(1)
    input_folder = sys.argv[1]
    output_folder = sys.argv[2]
    os.makedirs(output_folder, exist_ok=True)
    for fname in os.listdir(input_folder):
        if fname.endswith(".frd"):
            in_path = os.path.join(input_folder, fname)
            out_path = os.path.join(output_folder, fname)
            process_frd_file(in_path, out_path)


if __name__ == "__main__":
    main()
