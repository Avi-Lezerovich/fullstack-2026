import { useEffect } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import { Box, Divider, ToggleButton, ToggleButtonGroup, Tooltip } from "@mui/material";
import FormatBoldIcon from "@mui/icons-material/FormatBold";
import FormatItalicIcon from "@mui/icons-material/FormatItalic";
import FormatListBulletedIcon from "@mui/icons-material/FormatListBulleted";
import LinkIcon from "@mui/icons-material/Link";
import LinkOffIcon from "@mui/icons-material/LinkOff";

import type { Editor } from "@tiptap/react";

type Props = {
  /** Current HTML value (controlled-ish: only used to seed/reset the editor). */
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
};

/** Toolbar — Bold / Italic / Bullet list / Link, satisfying the WYSIWYG requirement. */
const Toolbar = ({ editor }: { editor: Editor }) => {
  const setLink = () => {
    const prev = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt("הדבק קישור (URL):", prev || "https://");
    if (url === null) return; // cancelled
    if (url === "") {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  };

  return (
    <Box sx={{ p: 0.5, display: "flex", gap: 0.5, flexWrap: "wrap" }}>
      <ToggleButtonGroup size="small">
        <Tooltip title="מודגש">
          <ToggleButton value="bold" selected={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}>
            <FormatBoldIcon fontSize="small" />
          </ToggleButton>
        </Tooltip>
        <Tooltip title="נטוי">
          <ToggleButton value="italic" selected={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}>
            <FormatItalicIcon fontSize="small" />
          </ToggleButton>
        </Tooltip>
        <Tooltip title="רשימה">
          <ToggleButton value="bulletList" selected={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>
            <FormatListBulletedIcon fontSize="small" />
          </ToggleButton>
        </Tooltip>
        <Tooltip title="קישור">
          <ToggleButton value="link" selected={editor.isActive("link")} onClick={setLink}>
            <LinkIcon fontSize="small" />
          </ToggleButton>
        </Tooltip>
        <Tooltip title="הסר קישור">
          <ToggleButton value="unlink" onClick={() => editor.chain().focus().unsetLink().run()} disabled={!editor.isActive("link")}>
            <LinkOffIcon fontSize="small" />
          </ToggleButton>
        </Tooltip>
      </ToggleButtonGroup>
    </Box>
  );
};

/**
 * Minimal WYSIWYG editor (TipTap) for post bodies. Emits HTML on every change.
 * The output is sanitized with DOMPurify at render time (see utils/htmlUtils).
 */
const RichTextEditor = ({ value, onChange, placeholder }: Props) => {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Link.configure({ openOnClick: false, autolink: true }),
    ],
    content: value,
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
    editorProps: {
      attributes: { dir: "rtl", style: "min-height:140px;outline:none;line-height:1.7;" },
    },
  });

  // Reset the document when the parent clears the value (e.g. after a successful submit).
  useEffect(() => {
    if (editor && value === "" && editor.getHTML() !== "<p></p>") {
      editor.commands.clearContent();
    }
  }, [value, editor]);

  if (!editor) return null;

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        "& .ProseMirror": { p: 1.5, minHeight: 140 },
        "& .ProseMirror p.is-editor-empty:first-of-type::before": {
          content: `"${placeholder || ""}"`,
          color: "text.disabled",
          float: "right",
          height: 0,
          pointerEvents: "none",
        },
        "& a": { color: "secondary.main", textDecoration: "underline" },
      }}
    >
      <Toolbar editor={editor} />
      <Divider />
      <EditorContent editor={editor} />
    </Box>
  );
};

export default RichTextEditor;
