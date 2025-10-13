namespace ExcelFinanceAddIn
{
    partial class RibbonFinance : Microsoft.Office.Tools.Ribbon.RibbonBase
    {
        private System.ComponentModel.IContainer components = null;

        internal Microsoft.Office.Tools.Ribbon.RibbonTab tabFinance;
        internal Microsoft.Office.Tools.Ribbon.RibbonGroup groupAPI;
        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnFetchAPI;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlCounterparty;
        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnSubmitCounterparty;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlCurrency;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlPeriod;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlBasis;
        internal Microsoft.Office.Tools.Ribbon.RibbonDropDown ddlType;
        internal Microsoft.Office.Tools.Ribbon.RibbonEditBox txtFromYear;
        internal Microsoft.Office.Tools.Ribbon.RibbonEditBox txtToYear;
        internal Microsoft.Office.Tools.Ribbon.RibbonButton btnFetchFinalData;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null)) components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            this.tabFinance = this.Factory.CreateRibbonTab();
            this.groupAPI = this.Factory.CreateRibbonGroup();
            this.btnFetchAPI = this.Factory.CreateRibbonButton();
            this.ddlCounterparty = this.Factory.CreateRibbonDropDown();
            this.btnSubmitCounterparty = this.Factory.CreateRibbonButton();
            this.ddlCurrency = this.Factory.CreateRibbonDropDown();
            this.ddlPeriod = this.Factory.CreateRibbonDropDown();
            this.ddlBasis = this.Factory.CreateRibbonDropDown();
            this.ddlType = this.Factory.CreateRibbonDropDown();
            this.txtFromYear = this.Factory.CreateRibbonEditBox();
            this.txtToYear = this.Factory.CreateRibbonEditBox();
            this.btnFetchFinalData = this.Factory.CreateRibbonButton();
            this.tabFinance.SuspendLayout();
            this.groupAPI.SuspendLayout();
            this.SuspendLayout();

            // Tab
            this.tabFinance.Label = "Finance Tools";
            this.tabFinance.Groups.Add(this.groupAPI);

            // Group
            this.groupAPI.Label = "API Workflow";
            this.groupAPI.Items.Add(this.btnFetchAPI);
            this.groupAPI.Items.Add(this.ddlCounterparty);
            this.groupAPI.Items.Add(this.btnSubmitCounterparty);
            this.groupAPI.Items.Add(this.ddlCurrency);
            this.groupAPI.Items.Add(this.ddlPeriod);
            this.groupAPI.Items.Add(this.ddlBasis);
            this.groupAPI.Items.Add(this.ddlType);
            this.groupAPI.Items.Add(this.txtFromYear);
            this.groupAPI.Items.Add(this.txtToYear);
            this.groupAPI.Items.Add(this.btnFetchFinalData);

            // Buttons
            this.btnFetchAPI.Label = "Fetch from API";
            this.btnFetchAPI.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnFetchAPI_Click);

            this.ddlCounterparty.Label = "Counterparty";
            this.ddlCounterparty.SelectionChanged += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.ddlCounterparty_SelectionChanged);

            this.btnSubmitCounterparty.Label = "Submit Counterparty";
            this.btnSubmitCounterparty.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnSubmitCounterparty_Click);

            this.ddlCurrency.Label = "Currency";
            this.ddlPeriod.Label = "Period";
            this.ddlBasis.Label = "Basis";
            this.ddlType.Label = "Type";

            this.txtFromYear.Label = "From Year";
            this.txtToYear.Label = "To Year";

            this.btnFetchFinalData.Label = "Fetch Final Data";
            this.btnFetchFinalData.Click += new Microsoft.Office.Tools.Ribbon.RibbonControlEventHandler(this.btnFetchFinalData_Click);

            this.Name = "RibbonFinance";
            this.RibbonType = "Microsoft.Excel.Workbook";
            this.Tabs.Add(this.tabFinance);

            this.tabFinance.ResumeLayout(false);
            this.groupAPI.ResumeLayout(false);
            this.ResumeLayout(false);
        }
    }
}

