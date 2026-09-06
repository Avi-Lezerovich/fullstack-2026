import Button from "@mui/material/Button";
import { Link as RouterLink } from "react-router-dom";

import { ErrorPage } from "../components/common/ErrorPage";

/**
 * The `*` route. It used to redirect to the feed, which made a typo'd address
 * indistinguishable from having asked for the feed in the first place.
 */
const NotFound = () => {
  return (
    <ErrorPage
      code="404"
      title="התיק לא נמצא בארכיון"
      description="מספר התיק שביקשת אינו רשום בפנקס בית המשפט. ייתכן שהכתובת הוקלדה בטעות, או שהתיק נגנז."
      action={
        <Button component={RouterLink} to="/" variant="contained">
          חזרה לאולם הראשי
        </Button>
      }
    />
  );
}; export default NotFound;
