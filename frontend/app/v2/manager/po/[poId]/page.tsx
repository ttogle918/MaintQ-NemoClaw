import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";

export default function PoDetailV2Page({ params }: { params: { poId: string } }) {
  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h5">MaintQ v2 (MUI) — {params.poId}</Typography>
    </Container>
  );
}
