using System;
using System.Collections.Generic;
using System.Data;
using System.Net.Http;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Office.Tools.Ribbon;
using Newtonsoft.Json;

namespace ExcelFinanceAddIn
{
    public partial class RibbonFinance : RibbonBase
    {
        // Required constructor calling base(factory)
        public RibbonFinance()
            : base(Globals.Factory.GetRibbonFactory())
        {
            InitializeComponent();
        }

        // Store API1 response
        public List<Counterparty> CounterpartyList { get; set; } = new List<Counterparty>();

        private async void btnFetchAPI_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                using (var client = new HttpClient())
                {
                    client.BaseAddress = new Uri("https://api.yourcompany.com/");
                    var resp = await client.GetAsync("counterparties");
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync();

                    var cpList = JsonConvert.DeserializeObject<List<Counterparty>>(json) ?? new List<Counterparty>();
                    var top5 = cpList.Count > 5 ? cpList.GetRange(0, 5) : cpList;

                    ddlCounterparty.Items.Clear();
                    foreach (var cp in top5)
                    {
                        var item = Factory.CreateRibbonDropDownItem();
                        item.Label = cp.CID;
                        ddlCounterparty.Items.Add(item);
                    }

                    CounterpartyList = top5;
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error fetching Counterparties: " + ex.Message);
            }
        }

        private void ddlCounterparty_SelectionChanged(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var selected = ddlCounterparty.SelectedItem;
                if (selected == null) return;
                var selectedCID = selected.Label;
                var cp = CounterpartyList.Find(c => c.CID == selectedCID);

                if (cp != null)
                {
                    string msg = $"CID\tCName\tShortName\n{cp.CID}\t{cp.CName}\t{cp.ShortName}";
                    MessageBox.Show(msg, "Counterparty Details");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error showing Counterparty: " + ex.Message);
            }
        }

        private async void btnSubmitCounterparty_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var sel = ddlCounterparty.SelectedItem;
                if (sel == null) { MessageBox.Show("Please select a counterparty."); return; }
                var selectedCID = sel.Label;
                var payload = new { CID = selectedCID };

                using (var client = new HttpClient())
                {
                    client.BaseAddress = new Uri("https://api.yourcompany.com/");
                    var content = new StringContent(JsonConvert.SerializeObject(payload),
                                                    System.Text.Encoding.UTF8, "application/json");
                    var resp = await client.PostAsync("api2", content);
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync();

                    dynamic api2Resp = JsonConvert.DeserializeObject(json);

                    // Populate dropdowns (clear then add items via Factory)
                    ddlCurrency.Items.Clear();
                    var currencyItem = Factory.CreateRibbonDropDownItem();
                    currencyItem.Label = api2Resp.Currency.ToString();
                    ddlCurrency.Items.Add(currencyItem);
                    ddlCurrency.SelectedItemIndex = 0;

                    ddlPeriod.Items.Clear();
                    foreach (var p in api2Resp.Period)
                    {
                        var it = Factory.CreateRibbonDropDownItem();
                        it.Label = p.ToString();
                        ddlPeriod.Items.Add(it);
                    }
                    ddlPeriod.SelectedItemIndex = 0;

                    ddlBasis.Items.Clear();
                    int basisIndex = 0;
                    foreach (var b in api2Resp.Basis)
                    {
                        var it = Factory.CreateRibbonDropDownItem();
                        it.Label = b.ToString();
                        ddlBasis.Items.Add(it);
                        // default to "text2" if present
                        if (b.ToString().Equals("text2", StringComparison.OrdinalIgnoreCase))
                            ddlBasis.SelectedItemIndex = basisIndex;
                        basisIndex++;
                    }

                    ddlType.Items.Clear();
                    foreach (var t in api2Resp.Type)
                    {
                        var it = Factory.CreateRibbonDropDownItem();
                        it.Label = t.ToString();
                        ddlType.Items.Add(it);
                    }
                    ddlType.SelectedItemIndex = 0;

                    txtFromYear.Text = api2Resp.FromYear.ToString();
                    txtToYear.Text = api2Resp.ToYear.ToString();
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error submitting Counterparty: " + ex.Message);
            }
        }

        private async void btnFetchFinalData_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var sel = ddlCounterparty.SelectedItem;
                if (sel == null) { MessageBox.Show("Please select a counterparty."); return; }

                var payload = new
                {
                    CID = sel.Label,
                    FromYear = int.Parse(txtFromYear.Text),
                    toYear = int.Parse(txtToYear.Text),
                    Period = ddlPeriod.SelectedItem?.Label,
                    Basis = ddlBasis.SelectedItem?.Label,
                    Type = ddlType.SelectedItem?.Label,
                };

                using (var client = new HttpClient())
                {
                    client.BaseAddress = new Uri("https://api.yourcompany.com/");
                    var content = new StringContent(JsonConvert.SerializeObject(payload),
                                                    System.Text.Encoding.UTF8, "application/json");

                    var resp = await client.PostAsync("api3", content);
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync();

                    // If API returns array of objects, convert to DataTable and write to Excel
                    DataTable dt;
                    try
                    {
                        dt = JsonConvert.DeserializeObject<DataTable>(json);
                    }
                    catch
                    {
                        // fallback: wrap single object into an array and try again
                        dt = JsonConvert.DeserializeObject<DataTable>("[" + json + "]");
                    }

                    Utils.ExcelWriter.WriteToExcel(dt, "Final Data");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error fetching final data: " + ex.Message);
            }
        }
    }

    public class Counterparty
    {
        public string CID { get; set; }
        public string CName { get; set; }
        public string ShortName { get; set; }
    }
}
