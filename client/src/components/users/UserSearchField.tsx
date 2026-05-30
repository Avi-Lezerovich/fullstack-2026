import { InputAdornment, TextField } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";

type UserSearchFieldProps = {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
};

const UserSearchField = ({ value, onChange }: UserSearchFieldProps) => (
  <TextField
    fullWidth
    placeholder="חיפוש לפי שם או אימייל..."
    value={value}
    onChange={onChange}
    sx={{ mb: 3, backgroundColor: "background.paper" }}
    InputProps={{
      startAdornment: (
        <InputAdornment position="start">
          <SearchIcon color="primary" />
        </InputAdornment>
      ),
    }}
  />
);

export default UserSearchField;
