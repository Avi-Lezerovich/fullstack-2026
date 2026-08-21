import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { SUMMONS_STATUS_LABELS, type Summons, type SummonsStatus } from "../../types";
import { initials } from "../../utils/format";

const STATUS_COLOR: Record<SummonsStatus, "default" | "success" | "error"> = {
  pending: "default",
  testified: "success",
  no_show: "error",
};

const SIDE_LABEL = { plaintiff: "עדי התביעה", defense: "עדי ההגנה" } as const;

const WitnessList = ({ summons }: { summons: Summons[] }) => {
  if (summons.length === 0) return null;

  const sides = (["plaintiff", "defense"] as const).filter((side) =>
    summons.some((s) => s.side === side),
  );

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }} data-testid="witness-list">
      <Typography variant="h6" gutterBottom>
        רשימת העדים
      </Typography>

      <Stack spacing={2}>
        {sides.map((side) => (
          <Box key={side}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              {SIDE_LABEL[side]}
            </Typography>
            <Stack spacing={1}>
              {summons
                .filter((s) => s.side === side)
                .map((s) => (
                  <Stack
                    key={s.id}
                    direction="row"
                    spacing={1.5}
                    alignItems="center"
                    data-testid="witness-row"
                    data-status={s.status}
                  >
                    <Avatar src={s.witness.avatar_url ?? undefined} sx={{ width: 30, height: 30 }}>
                      {initials(s.witness.name)}
                    </Avatar>
                    <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>
                      {s.witness.name}
                    </Typography>
                    <Chip
                      size="small"
                      variant="outlined"
                      color={STATUS_COLOR[s.status]}
                      label={SUMMONS_STATUS_LABELS[s.status]}
                    />
                  </Stack>
                ))}
            </Stack>
          </Box>
        ))}
      </Stack>
    </Paper>
  );
}; export default WitnessList;
