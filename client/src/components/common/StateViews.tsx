import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

/** The three states every data-loading view needs, so no page reinvents them. */

export const Loading = ({ label = "טוען…" }: { label?: string }) => {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 2, py: 6 }}>
      <CircularProgress size={28} />
      <Typography color="text.secondary">{label}</Typography>
    </Box>
  );
};

export const ErrorNote = ({ message }: { message: string }) => {
  return (
    <Alert severity="error" sx={{ my: 2 }} data-testid="error-note">
      {message}
    </Alert>
  );
};

export const EmptyState = ({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) => {
  return (
    <Box sx={{ textAlign: "center", py: 6, px: 2 }} data-testid="empty-state">
      <Typography variant="h6" gutterBottom>
        {title}
      </Typography>
      {description && (
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
      )}
      {action}
    </Box>
  );
};
