find pdg -name '*.dot' -exec sh -c '
  for f do
	dot -Tsvg "$f" -o "${f%.dot}.svg"
  done
' sh {} +
