using System;
using System.Windows.Forms;

public partial class PasswordPrompt : Form
{
    public string Password => textBox1.Text;

    public PasswordPrompt()
    {
        InitializeComponent();
        textBox1.PasswordChar = '*';
    }

    private void btnOK_Click(object sender, EventArgs e)
    {
        DialogResult = DialogResult.OK;
        Close();
    }

    private void btnCancel_Click(object sender, EventArgs e)
    {
        DialogResult = DialogResult.Cancel;
        Close();
    }
}


private static readonly string password = ShowPasswordDialog();

private static string ShowPasswordDialog()
{
    using (var prompt = new PasswordPrompt())
    {
        if (prompt.ShowDialog() == DialogResult.OK)
            return prompt.Password;
    }
    return "";
}
