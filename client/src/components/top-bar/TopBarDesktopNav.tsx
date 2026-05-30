import { Button, Stack } from "@mui/material";

const NAV_ITEMS = [
  { href: "#home", label: "Home" },
  { href: "#about", label: "About" },
  { href: "#contact", label: "Contact" },
];

export const TopBarDesktopNav = () => (
  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ justifyContent: "flex-end" }}>
    {NAV_ITEMS.map((item) => (
      <Button
        key={item.href}
        href={item.href}
        sx={{
          color: "#FAF6E9",
          borderRadius: 999,
          px: 2,
          "&:hover": { backgroundColor: "rgba(250, 246, 233, 0.08)" },
        }}
      >
        {item.label}
      </Button>
    ))}
  </Stack>
);
