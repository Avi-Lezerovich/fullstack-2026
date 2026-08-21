import { useCallback, useEffect, useState } from "react";
import Badge from "@mui/material/Badge";
import IconButton from "@mui/material/IconButton";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import { Link as RouterLink, useLocation } from "react-router-dom";

import { fetchConversations } from "../../api";

interface MessagesLinkProps {
  /**
   * Id of the newest `message` notification, from `useNotifications`. Any
   * change to it means a DM arrived and the count below is stale.
   */
  messageSignal: number;
}

/**
 * The inbox button and its unread count.
 *
 * The count is refetched on three triggers: mount, a `message` notification
 * arriving, and a navigation — the last one is what clears the badge after the
 * user has read a thread, since marking-as-read happens server-side when the
 * thread is opened.
 */
const MessagesLink = ({ messageSignal }: MessagesLinkProps) => {
  const location = useLocation();
  const [unread, setUnread] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const { unread_total } = await fetchConversations();
      setUnread(unread_total);
    } catch {
      // A failed count is not worth an error banner in the app bar.
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, messageSignal, location.pathname]);

  return (
    <IconButton
      component={RouterLink}
      to="/messages"
      aria-label="הודעות"
      data-testid="messages-link"
      sx={{ color: "primary.contrastText" }}
    >
      <Badge badgeContent={unread} color="secondary" max={99} data-testid="messages-unread">
        <MailOutlineIcon />
      </Badge>
    </IconButton>
  );
};

export default MessagesLink;
