import { useCallback } from "react";

import * as api from "../../api";
import UserListDialog from "../common/UserListDialog";

interface Props {
  open: boolean;
  caseId: number;
  onClose: () => void;
}

/** The list behind a like count. The list itself is UserListDialog, which the
 *  follower list shares. */
const LikersDialog = ({ open, caseId, onClose }: Props) => {
  const load = useCallback(() => api.fetchLikers(caseId), [caseId]);

  return (
    <UserListDialog
      open={open}
      title="מי אהב את התביעה"
      emptyTitle="עוד אף אחד"
      load={load}
      onClose={onClose}
      testId="likers-dialog"
      rowTestId="liker-row"
    />
  );
}; export default LikersDialog;
