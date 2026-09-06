import { useCallback } from "react";

import * as api from "../../api";
import UserListDialog from "../common/UserListDialog";

interface Props {
  open: boolean;
  caseId: number;
  onClose: () => void;
}

/** The list behind a follower count — "N users tracking this". */
const FollowersDialog = ({ open, caseId, onClose }: Props) => {
  const load = useCallback(() => api.fetchFollowers(caseId), [caseId]);

  return (
    <UserListDialog
      open={open}
      title="מי עוקב אחרי התביעה"
      emptyTitle="עוד אף אחד לא עוקב"
      load={load}
      onClose={onClose}
      testId="followers-dialog"
      rowTestId="follower-row"
    />
  );
}; export default FollowersDialog;
