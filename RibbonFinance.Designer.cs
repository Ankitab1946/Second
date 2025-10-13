namespace ExcelFinanceAddIn
{
    partial class RibbonFinance
    {
        private System.ComponentModel.IContainer components = null;

        internal Microsoft.Office.Tools.Ribbon.RibbonTab tabFinance;
        internal Microsoft.Office.Tools.Ribbon.RibbonGroup grpDataFetch;
        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnFetchAPI;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlCounterparty;
        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnSubmitCounterparty;

        internal Microsoft.Office.Tools.Ribbon.RibbonGroup grpParameters;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlCurrency;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlPeriod;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlBasis;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlType;
        internal Microsoft.Office.Tools.Ribbon.RibbonEditBox txtFromYear;
        internal Microsoft.Office.Tools.Ribbon.RibbonEditBox txtToYear;

        internal Microsoft.Office.Tools.Ribbon.RibbonGroup grpOutput;
        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnFetchFinalData;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            this.tabFinance = this.Factory.CreateRibbonTab();
            this.grpDataFetch = this.Factory.CreateRibbonGroup();
            this.btnFetchAPI = this.Factory.CreateRibbonButton();
            this.ddlCounterparty = this.Factory.CreateRibbonDropDown();
            this.btnSubmitCounterparty = this.Factory.CreateRibbonButton();

            this.grpParameters = this.Factory.CreateRibbonGroup();
            this.ddlCurrency = this.Factory.CreateRibbonDropDown();
            this.ddlPeriod = this.Factory.CreateRibbonDropDown();
            this.ddlBasis = this.Factory.CreateRibbonDropDown();
            this.ddlType = this.Factory.CreateRibbonDropDown();
            this.txtFromYear = this.Factory.CreateRibbonEditBox();
            this.txtToYear = this.Factory.CreateRibbonEditBox();

            this.grpOutput = this.Factory.CreateRibbonGroup();
            this.btnFetchFinalData = this.Factory.CreateRibbonButton();

            this.tabFinance.SuspendLayout();
            this.grpDataFetch.SuspendLayout();
            this.grpParameters.SuspendLayout();
            this.grpOutput.SuspendLayout();
            this.SuspendLayout();

            // === Tab ===
            this.tabFinance.Label = "Finance Tools";
            this.tabFinance.Groups.Add(this.grpDataFetch);
            this.tabFinance.Groups.Add(this.grpParameters);
            this.tabFinance.Groups.Add(this.grpOutput);

            // === Group: Data Fetch ===
            this.grpDataFetch.Label = "Data Retrieval";
            this.grpDataFetch.Items.Add(this.btnFetchAPI);
            this.grpDataFetch.Items.Add(this.ddlCounterparty);
            this.grpDataFetch.Items.Add(this.btnSubmitCounterparty);

            this.btnFetchAPI.Label = "Fetch from API";
            this.btnFetchAPI.ShowImage = true;
            this.btnFetchAPI.Image = Properties.Resources.cloud_download_32;  // Add icon in Resources
            this.btnFetchAPI.ScreenTip = "Fetch Counterparty list from API";
            this.btnFetchAPI.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnFetchAPI_Click);

            this.ddlCounterparty.Label = "Counterparty";
            var placeholder = this.Factory.CreateRibbonDropDownItem();
            placeholder.Label = "Select Counterparty...";
            this.ddlCounterparty.Items.Add(placeholder);
            this.ddlCounterparty.SelectedItemIndex = 0;
            this.ddlCounterparty.SelectionChanged += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.ddlCounterparty_SelectionChanged);

            this.btnSubmitCounterparty.Label = "Submit";
            this.btnSubmitCounterparty.ShowImage = true;
            this.btnSubmitCounterparty.Image = Properties.Resources.send_32;
            this.btnSubmitCounterparty.ScreenTip = "Submit selected Counterparty";
            this.btnSubmitCounterparty.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnSubmitCounterparty_Click);

            // === Group: Parameters ===
            this.grpParameters.Label = "API Parameters";
            this.grpParameters.Items.Add(this.ddlCurrency);
            this.grpParameters.Items.Add(this.ddlPeriod);
            this.grpParameters.Items.Add(this.ddlBasis);
            this.grpParameters.Items.Add(this.ddlType);
            this.grpParameters.Items.Add(this.txtFromYear);
            this.grpParameters.Items.Add(this.txtToYear);

            this.ddlCurrency.Label = "Currency";
            this.ddlPeriod.Label = "Period";
            this.ddlBasis.Label = "Basis";
            this.ddlType.Label = "Type";

            this.txtFromYear.Label = "From Year";
            this.txtFromYear.Text = "2007";
            this.txtToYear.Label = "To Year";
            this.txtToYear.Text = "2008";

            // === Group: Output ===
            this.grpOutput.Label = "Excel Output";
            this.grpOutput.Items.Add(this.btnFetchFinalData);

            this.btnFetchFinalData.Label = "Fetch Final Data";
            this.btnFetchFinalData.ShowImage = true;
            this.btnFetchFinalData.Image = Properties.Resources.table_32;
            this.btnFetchFinalData.ScreenTip = "Fetch Final Balance Sheet and display in Excel";
            this.btnFetchFinalData.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnFetchFinalData_Click);

            // === Add to Tab ===
            this.Name = "RibbonFinance";
            this.RibbonType = "Microsoft.Excel.Workbook";
            this.Tabs.Add(this.tabFinance);

            this.tabFinance.ResumeLayout(false);
            this.grpDataFetch.ResumeLayout(false);
            this.grpParameters.ResumeLayout(false);
            this.grpOutput.ResumeLayout(false);
            this.ResumeLayout(false);
        }
    }
}
