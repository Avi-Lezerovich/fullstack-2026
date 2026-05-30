import { Box, Button, CircularProgress } from "@mui/material";

type LoadMoreButtonProps = {
  loadingMore: boolean;
  onLoadMore: () => void;
};

const LoadMoreButton = ({ loadingMore, onLoadMore }: LoadMoreButtonProps) => (
  <Box sx={{ display: "flex", justifyContent: "center", pt: 3 }}>
    <Button
      variant="outlined"
      onClick={onLoadMore}
      disabled={loadingMore}
      startIcon={loadingMore ? <CircularProgress size={18} /> : null}
    >
      {loadingMore ? "טוען..." : "טען עוד"}
    </Button>
  </Box>
);

export default LoadMoreButton;
